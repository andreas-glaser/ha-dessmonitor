"""Hybrid cloud coordinator with preferred local telemetry and cloud fallback."""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Container
from math import isfinite
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .. import DessMonitorDataUpdateCoordinator
from ..api import DessMonitorAPI
from ..const import CONF_LOCAL_COLLECTOR_IP, CONF_LOCAL_COLLECTOR_IPS
from ..data_sources import with_data_source
from ..device_support import map_sensor_title
from ..sensor_titles import cumulative_sensor_key
from .coordinator import DessMonitorLocalCoordinator

_LOGGER = logging.getLogger(__name__)

# A cumulative counter that drops by less than this fraction is two sources
# disagreeing about the same total; a larger drop is a real reset.
_CUMULATIVE_RESET_RATIO = 0.9

# Collectors a sole-device pairing has already been reported for, so the
# override is visible once rather than on every poll.
_REPORTED_SOLE_DEVICE_PAIRINGS: set[tuple[str, str]] = set()

# Collectors an unpaired local device has already been reported for, keyed by
# the addresses involved, so a changed situation is reported again.
_REPORTED_UNPAIRED_LOCAL: set[tuple[str, tuple[Any, ...], tuple[Any, ...]]] = set()


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
        self._cumulative_high: dict[tuple[str, str], tuple[float, Any]] = {}

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
        try:
            if not self.api.token or not self.api.secret:
                if not await self.api.load_saved_token():
                    await self.api.authenticate()
            cloud_data = await super()._async_update_data()
        except Exception as err:  # pylint: disable=broad-except
            self._cloud_stale = True
            self.stale_cloud_serials = frozenset(self._cached_cloud_data)
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
                return self._merge(
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
                return self._merge(
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
                return self._merge(
                    self._cached_cloud_data,
                    local_data,
                    local_available=local_available,
                )
            raise

        self._cloud_stale = False
        self._initial_refresh_completed = True
        # Discovery/disconnection can finish while the cloud request awaits IO.
        # Do not overwrite a newer local push with the pre-request snapshot.
        local_data = self._current_local_data()
        return self._merge(
            cloud_data,
            local_data,
            local_available=bool(local_data),
            stale_serials=self.stale_cloud_serials,
        )

    def _merge(
        self,
        cloud_data: dict[str, Any] | None,
        local_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Overlay local telemetry, then arbitrate the cumulative counters."""
        return self._hold_cumulative_totals(
            merge_cloud_and_local(cloud_data, local_data, **kwargs)
        )

    def _hold_cumulative_totals(self, merged: dict[str, Any]) -> dict[str, Any]:
        """Keep a cumulative counter from stepping back when its source changes.

        The local driver reads the lifetime counter once a minute and the cloud
        reports its own every five, so the two are stale by different amounts
        and whichever is publishing can be behind the other. Home Assistant
        reads a decrease on a ``total_increasing`` sensor as a meter reset. The
        reporter in #53 saw Energy Total step from 10113.896 to 10113.801 kWh
        across a source switch and Home Assistant log the entity for it.

        Only a small step back is held: a drop past
        ``_CUMULATIVE_RESET_RATIO`` is a genuine reset - midnight on Energy
        Today, or replaced hardware - and is published as reported. The value
        held is the earlier source's own, so no reading is ever synthesised.
        """
        for serial, payload in merged.items():
            devcode = payload.get("device", {}).get("devcode")
            for point in payload.get("data", []):
                key = _cumulative_key(devcode, point.get("title"))
                if key is None:
                    continue
                value = _as_float(point.get("val"))
                if value is None:
                    continue
                mark = (serial, key)
                held = self._cumulative_high.get(mark)
                if held is not None and (
                    held[0] > value >= held[0] * _CUMULATIVE_RESET_RATIO
                ):
                    point["val"] = held[1]
                    continue
                self._cumulative_high[mark] = (value, point["val"])
        return merged

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
        merged = self._merge(
            self._cached_cloud_data,
            local_data,
            local_available=bool(local_data),
            cloud_source="Cached Cloud" if self._cloud_stale else "Cloud",
            stale_serials=self.stale_cloud_serials,
        )
        if not merged:
            # A local failure also notifies this listener. With no cloud
            # snapshot to fall back on, publishing an empty one as a success
            # would clear the cloud failure and claim a working coordinator
            # while neither transport has ever delivered a device.
            return
        self.data = merged
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


def _cumulative_key(raw_device_code: Any, title: Any) -> str | None:
    """Return the canonical key of a reading that only ever counts upwards."""
    if not isinstance(title, str) or not title.strip():
        return None
    try:
        device_code = int(raw_device_code)
    except (TypeError, ValueError):
        device_code = 0
    mapped = map_sensor_title(device_code, title) if device_code else title
    return cumulative_sensor_key(mapped, title)


def _as_float(value: Any) -> float | None:
    """Return a finite float for a reading, or None when it is not numeric."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def merge_cloud_and_local(
    cloud_data: dict[str, Any] | None,
    local_data: dict[str, Any] | None,
    *,
    local_available: bool,
    cloud_source: str = "Cloud",
    stale_serials: Container[str] = (),
) -> dict[str, Any]:
    """Overlay local values onto the matching cloud device without mutating inputs.

    ``stale_serials`` names the devices whose cloud payload the coordinator
    retained from an earlier cycle. A local overlay still makes such a device
    live, but without one it keeps the cached label rather than claiming the
    cloud answered for it.
    """
    merged = copy.deepcopy(cloud_data or {})
    local_devices = local_data or {}
    matched_local: set[str] = set()
    cloud_per_collector = _devices_per_collector(merged)
    local_per_collector = _devices_per_collector(local_devices, skip_unverified=True)

    def source_for(cloud_serial: str) -> str:
        return "Cached Cloud" if cloud_serial in stale_serials else cloud_source

    if local_available:
        for cloud_serial, cloud_payload in merged.items():
            local_match = _find_local_match(
                cloud_serial,
                cloud_payload,
                local_devices,
                matched_local,
                cloud_per_collector,
                local_per_collector,
            )
            if local_match is None:
                cloud_payload["data"] = with_data_source(
                    cloud_payload.get("data", []), source_for(cloud_serial)
                )
                continue
            local_serial, local_payload = local_match
            matched_local.add(local_serial)
            cloud_payload["data"] = _merge_data_points(
                cloud_payload.get("data", []),
                local_payload.get("data", []),
                cloud_payload.get("device", {}).get("devcode"),
            )

        _report_unpaired_local(merged, local_devices, matched_local)

    else:
        for cloud_serial, cloud_payload in merged.items():
            cloud_payload["data"] = with_data_source(
                cloud_payload.get("data", []), source_for(cloud_serial)
            )

    return merged


def _report_unpaired_local(
    cloud_devices: dict[str, Any],
    local_devices: dict[str, Any],
    matched_local: set[str],
) -> None:
    """Say once that a collector answered for a device nothing could be paired to.

    The refusal used to be entirely silent: in #61 local telemetry was flowing
    and ``Data Source`` stayed on ``Cloud``, and the owner found the fix by
    setting **Inverter address** on a hunch. Where one device sits behind the
    collector the overlay now pairs it regardless of the address; where several
    do, pairing on anything weaker than an address would risk attributing one
    inverter's readings to another, so this reports what it saw instead (#65).
    """
    for collector, addresses in _unpaired_addresses(local_devices, matched_local):
        cloud_addresses = tuple(
            sorted(
                str(payload.get("device", {}).get("devaddr"))
                for payload in cloud_devices.values()
                if str(payload.get("collector", {}).get("pn", "")) == collector
            )
        )
        if not cloud_addresses:
            # The cloud does not list this collector at all, which is not an
            # address problem and has nothing for the owner to set.
            continue
        seen = (collector, addresses, cloud_addresses)
        if seen in _REPORTED_UNPAIRED_LOCAL:
            continue
        _REPORTED_UNPAIRED_LOCAL.add(seen)
        _LOGGER.warning(
            "Collector %s answered locally for RS485 address(es) %s, which match "
            "none of the addresses the cloud records for it (%s), so that local "
            "telemetry is not published. Set the integration's Inverter address "
            "option to the address the collector answers on",
            collector,
            ", ".join(addresses),
            ", ".join(cloud_addresses),
        )


def _unpaired_addresses(
    local_devices: dict[str, Any], matched_local: set[str]
) -> list[tuple[str, tuple[str, ...]]]:
    """Group the local devices nothing was paired with by their collector."""
    by_collector: dict[str, list[str]] = {}
    for local_serial, payload in local_devices.items():
        if local_serial in matched_local:
            continue
        device = payload.get("device", {})
        if device.get("local_address_verified") is False:
            continue
        collector = str(payload.get("collector", {}).get("pn", ""))
        if not collector:
            continue
        by_collector.setdefault(collector, []).append(str(device.get("devaddr")))
    return [
        (collector, tuple(sorted(addresses)))
        for collector, addresses in sorted(by_collector.items())
    ]


def _devices_per_collector(
    devices: dict[str, Any], *, skip_unverified: bool = False
) -> dict[str, int]:
    """Count how many devices each collector product number carries."""
    counts: dict[str, int] = {}
    for payload in devices.values():
        if (
            skip_unverified
            and payload.get("device", {}).get("local_address_verified") is False
        ):
            continue
        collector = str(payload.get("collector", {}).get("pn", ""))
        if collector:
            counts[collector] = counts.get(collector, 0) + 1
    return counts


def _find_local_match(
    cloud_serial: str,
    cloud_payload: dict[str, Any],
    local_devices: dict[str, Any],
    already_matched: set[str],
    cloud_per_collector: dict[str, int] | None = None,
    local_per_collector: dict[str, int] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Match by stable serial, then collector PN plus RS485 address, then sole device."""
    if cloud_serial in local_devices and cloud_serial not in already_matched:
        return cloud_serial, local_devices[cloud_serial]

    cloud_collector = str(cloud_payload.get("collector", {}).get("pn", ""))
    cloud_address = cloud_payload.get("device", {}).get("devaddr")
    candidates: list[tuple[str, dict[str, Any]]] = []
    for local_serial, local_payload in local_devices.items():
        if local_serial in already_matched:
            continue
        local_collector = str(local_payload.get("collector", {}).get("pn", ""))
        if local_payload.get("device", {}).get("local_address_verified") is False:
            continue
        if not cloud_collector or cloud_collector != local_collector:
            continue
        local_address = local_payload.get("device", {}).get("devaddr")
        if cloud_address is not None and cloud_address == local_address:
            return local_serial, local_payload
        candidates.append((local_serial, local_payload))

    return _sole_device_match(
        cloud_serial,
        cloud_collector,
        cloud_address,
        candidates,
        cloud_per_collector or {},
        local_per_collector or {},
    )


def _sole_device_match(
    cloud_serial: str,
    cloud_collector: str,
    cloud_address: Any,
    candidates: list[tuple[str, dict[str, Any]]],
    cloud_per_collector: dict[str, int],
    local_per_collector: dict[str, int],
) -> tuple[str, dict[str, Any]] | None:
    """Pair the one device behind a collector with the one the cloud lists for it.

    Automatic discovery pairs on whichever RS485 address answers first, and the
    cloud's record of that address can differ: the collector in #61 answered on
    address 5 against a different cloud record, so local telemetry was flowing
    and the overlay declined it in silence, leaving ``Data Source`` on ``Cloud``
    in ``prefer_local`` mode until the owner set **Inverter address** by hand.

    Where one collector carries exactly one cloud device and answers for
    exactly one local device, there is nothing the pairing could get wrong and
    the addresses need not agree. Anything less certain than that still
    refuses: a wrong pairing publishes one inverter's telemetry on another's
    entities, and the owner has no way to tell (#61, #65).
    """
    if not cloud_collector or len(candidates) != 1:
        return None
    if cloud_per_collector.get(cloud_collector) != 1:
        return None
    if local_per_collector.get(cloud_collector) != 1:
        return None

    local_serial, local_payload = candidates[0]
    seen = (cloud_collector, cloud_serial)
    if seen not in _REPORTED_SOLE_DEVICE_PAIRINGS:
        _REPORTED_SOLE_DEVICE_PAIRINGS.add(seen)
        _LOGGER.info(
            "Collector %s carries one inverter locally and one in the cloud, so "
            "local telemetry is paired with %s although the RS485 addresses "
            "differ (local %s, cloud %s). Set the inverter address to the local "
            "one to pair on the address instead",
            cloud_collector,
            cloud_serial,
            local_payload.get("device", {}).get("devaddr"),
            cloud_address,
        )
    return local_serial, local_payload


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

    def key_for(point: dict[str, Any]) -> str:
        title = str(point.get("title", "")).strip()
        return (
            map_sensor_title(device_code, title) if device_code else title
        ).casefold()

    local_by_key: dict[str, dict[str, Any]] = {}
    for point in local_points:
        key = key_for(point)
        if key and key != "data source":
            local_by_key[key] = point

    result: list[dict[str, Any]] = []
    overlaid: set[str] = set()
    for point in cloud_points:
        key = key_for(point)
        if not key or key == "data source":
            continue
        if key not in local_by_key:
            # Main and Current priority can map to the same sensor key but
            # are distinct cloud controls. Retain both raw fields and order.
            result.append(copy.deepcopy(point))
        elif key not in overlaid:
            result.append(copy.deepcopy(local_by_key[key]))
            overlaid.add(key)
    result.extend(
        copy.deepcopy(point)
        for key, point in local_by_key.items()
        if key not in overlaid
    )
    return result + [{"title": "Data Source", "val": "Local", "unit": ""}]
