"""Hybrid cloud coordinator with preferred local telemetry and cloud fallback."""

from __future__ import annotations

import asyncio
import copy
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .. import DessMonitorDataUpdateCoordinator
from ..api import DessMonitorAPI
from ..const import CONF_LOCAL_COLLECTOR_IP, CONF_LOCAL_COLLECTOR_IPS
from ..device_support import map_sensor_title
from .coordinator import DessMonitorLocalCoordinator

_LOGGER = logging.getLogger(__name__)


class DessMonitorHybridCoordinator(DessMonitorDataUpdateCoordinator):
    """Combine fresh local readings with cloud metadata, controls, and fallback."""

    is_hybrid = True

    def __init__(
        self,
        hass: HomeAssistant,
        api: DessMonitorAPI,
        update_interval: int,
        local_config: dict[str, Any],
        entry_id: str,
        *,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        # Hybrid owns per-device local/cloud arbitration below, so the base
        # API coordinator must surface failures instead of consuming them as
        # an API-only cached fallback.
        super().__init__(
            hass,
            api,
            update_interval,
            entry_id=entry_id,
            allow_cached_fallback=False,
            config_entry=config_entry,
        )
        collector_ips = _configured_collector_ips(local_config)
        self.locals = tuple(
            DessMonitorLocalCoordinator(
                hass, {**local_config, CONF_LOCAL_COLLECTOR_IP: collector_ip}
            )
            for collector_ip in collector_ips
        )
        # Kept as a small compatibility surface for entity/tests that inspect
        # the first configured local transport.
        self.local = self.locals[0]
        self._initial_refresh_completed = False
        self._remove_local_listeners = tuple(
            local.async_add_listener(self._handle_local_update) for local in self.locals
        )
        self.local_setup_errors: list[str] = []
        self._shutdown = False
        self._cloud_stale = False
        self._local_push_handle: asyncio.TimerHandle | None = None

    async def async_setup_local(self) -> None:
        """Start optional local services without weakening cloud availability."""
        # API-only and hybrid modes deliberately share the same snapshot store
        # so enabling or disabling preferred-local mode never loses fallback
        # metadata or canonical device identities.
        await self.async_setup_cloud_cache()
        for local in self.locals:
            try:
                await local.async_setup()
            except OSError as err:
                self.local_setup_errors.append(str(err))
                await local.async_shutdown()
                _LOGGER.error(
                    "One local telemetry route could not start; using cloud fallback: %s",
                    err,
                )

    async def async_shutdown(self) -> None:
        """Stop local services and close the inherited cloud API client."""
        if self._shutdown:
            return
        self._shutdown = True
        if self._local_push_handle is not None:
            self._local_push_handle.cancel()
            self._local_push_handle = None
        for remove_listener in self._remove_local_listeners:
            remove_listener()
        results = await asyncio.gather(
            *(local.async_shutdown() for local in self.locals),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.warning("Local telemetry shutdown failed: %s", result)
        await super().async_shutdown()

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh cloud state, then overlay healthy local measurements."""
        local_data = self._current_local_data()
        local_available = bool(local_data)
        try:
            if not self.api.token or not self.api.secret:
                if not await self.api.load_saved_token():
                    await self.api.authenticate()
            cloud_data = await super()._async_update_data()
        except Exception as err:  # pylint: disable=broad-except
            self._cloud_stale = True
            # A collector may finish its callback/discovery while a slow cloud
            # request is in flight. Re-read here so that failure handling uses
            # the freshest local state instead of the pre-request snapshot.
            local_data = self._current_local_data()
            local_available = bool(local_data)
            if local_available:
                _LOGGER.warning(
                    "DessMonitor cloud refresh failed; continuing with local telemetry: %s",
                    err,
                )
                self._initial_refresh_completed = True
                return merge_cloud_and_local(
                    self._cached_cloud_data,
                    local_data,
                    local_available=True,
                    cloud_source="Cached Cloud",
                )
            if self._cached_cloud_data:
                _LOGGER.warning(
                    "Both live transports are unavailable; retaining the last cloud snapshot"
                )
                self._initial_refresh_completed = True
                return merge_cloud_and_local(
                    self._cached_cloud_data,
                    local_data,
                    local_available=False,
                    cloud_source="Cached Cloud",
                )
            if not self._initial_refresh_completed:
                _LOGGER.warning(
                    "Cloud is unavailable during hybrid startup; waiting for local telemetry"
                )
                self._initial_refresh_completed = True
                return merge_cloud_and_local(
                    self._cached_cloud_data,
                    local_data,
                    local_available=local_available,
                )
            raise

        self._cloud_stale = False
        self._initial_refresh_completed = True
        return merge_cloud_and_local(
            cloud_data,
            local_data,
            local_available=local_available,
        )

    def _handle_local_update(self) -> None:
        """Coalesce near-simultaneous collector polls into one HA update."""
        if (
            not self._initial_refresh_completed
            or self._shutdown
            or self._local_push_handle is not None
        ):
            return
        self._local_push_handle = asyncio.get_running_loop().call_later(
            0.1, self._publish_local_update
        )

    def _publish_local_update(self) -> None:
        """Publish local data without postponing the independent cloud refresh."""
        self._local_push_handle = None
        if self._shutdown:
            return
        local_data = self._current_local_data()
        self.data = merge_cloud_and_local(
            self._cached_cloud_data,
            local_data,
            local_available=bool(local_data),
            cloud_source="Cached Cloud" if self._cloud_stale else "Cloud",
        )
        self.last_exception = None
        self.last_update_success = True
        # DataUpdateCoordinator.async_set_updated_data() resets its refresh
        # timer. Local pushes arrive much faster than the API interval, so using
        # it here would postpone cloud refreshes forever. Notify listeners
        # directly and leave the existing cloud schedule untouched.
        self.async_update_listeners()

    def _current_local_data(self) -> dict[str, Any]:
        """Combine only healthy local snapshots without losing duplicate serials."""
        combined: dict[str, Any] = {}
        for local in self.locals:
            if not local.last_update_success or not isinstance(local.data, dict):
                continue
            for serial, payload in local.data.items():
                key = serial
                if key in combined:
                    collector_pn = str(payload.get("collector", {}).get("pn", "local"))
                    key = f"{serial}@{collector_pn}"
                combined[key] = payload
        return combined


def _configured_collector_ips(local_config: dict[str, Any]) -> tuple[str, ...]:
    """Read the multi-collector option with legacy single-IP compatibility."""
    configured = local_config.get(CONF_LOCAL_COLLECTOR_IPS)
    if isinstance(configured, list):
        values = configured
    elif isinstance(configured, str):
        values = configured.replace("\n", ",").split(",")
    else:
        values = [local_config.get(CONF_LOCAL_COLLECTOR_IP, "")]
    result = tuple(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )
    if not result:
        raise ValueError("hybrid mode requires at least one collector IP")
    return result


def merge_cloud_and_local(
    cloud_data: dict[str, Any] | None,
    local_data: dict[str, Any] | None,
    *,
    local_available: bool,
    cloud_source: str = "Cloud",
) -> dict[str, Any]:
    """Overlay local values onto the matching cloud device without mutating inputs."""
    merged = copy.deepcopy(cloud_data or {})
    local_devices = local_data or {}
    matched_local: set[str] = set()

    if local_available:
        for cloud_serial, cloud_payload in merged.items():
            local_match = _find_local_match(
                cloud_serial, cloud_payload, local_devices, matched_local
            )
            if local_match is None:
                cloud_payload["data"] = _with_data_source(
                    cloud_payload.get("data", []), cloud_source
                )
                continue
            local_serial, local_payload = local_match
            matched_local.add(local_serial)
            cloud_payload["data"] = _merge_data_points(
                cloud_payload.get("data", []),
                local_payload.get("data", []),
                cloud_payload.get("device", {}).get("devcode"),
            )

    else:
        for cloud_payload in merged.values():
            cloud_payload["data"] = _with_data_source(
                cloud_payload.get("data", []), cloud_source
            )

    return merged


def _find_local_match(
    cloud_serial: str,
    cloud_payload: dict[str, Any],
    local_devices: dict[str, Any],
    already_matched: set[str],
) -> tuple[str, dict[str, Any]] | None:
    """Match by stable serial first, then collector PN plus RS485 address."""
    if cloud_serial in local_devices and cloud_serial not in already_matched:
        return cloud_serial, local_devices[cloud_serial]

    cloud_collector = str(cloud_payload.get("collector", {}).get("pn", ""))
    cloud_address = cloud_payload.get("device", {}).get("devaddr")
    for local_serial, local_payload in local_devices.items():
        if local_serial in already_matched:
            continue
        local_collector = str(local_payload.get("collector", {}).get("pn", ""))
        local_address = local_payload.get("device", {}).get("devaddr")
        if (
            cloud_collector
            and cloud_collector == local_collector
            and cloud_address is not None
            and cloud_address == local_address
        ):
            return local_serial, local_payload
    return None


def _merge_data_points(
    cloud_points: list[dict[str, Any]],
    local_points: list[dict[str, Any]],
    raw_device_code: Any,
) -> list[dict[str, Any]]:
    """Prefer normalized local values while retaining cloud-only measurements."""
    try:
        device_code = int(raw_device_code)
    except (TypeError, ValueError):
        device_code = 0

    indexed: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for point in cloud_points:
        raw_title = str(point.get("title", "")).strip()
        if not raw_title:
            continue
        title = map_sensor_title(device_code, raw_title) if device_code else raw_title
        if title not in indexed:
            order.append(title)
        indexed[title] = copy.deepcopy(point)

    for point in local_points:
        title = str(point.get("title", "")).strip()
        if not title or title == "Data Source":
            continue
        if title not in indexed:
            order.append(title)
        indexed[title] = copy.deepcopy(point)

    order = [title for title in order if title != "Data Source"]
    return [indexed[title] for title in order] + [
        {"title": "Data Source", "val": "Local", "unit": ""}
    ]


def _with_data_source(
    points: list[dict[str, Any]], source: str
) -> list[dict[str, Any]]:
    """Replace the synthetic data-source point while retaining all measurements."""
    result = [
        copy.deepcopy(point) for point in points if point.get("title") != "Data Source"
    ]
    result.append({"title": "Data Source", "val": source, "unit": ""})
    return result
