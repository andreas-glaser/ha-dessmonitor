"""The DessMonitor integration."""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DessMonitorAPI, DessMonitorError
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_MODE,
    CONF_UPDATE_INTERVAL,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_LOCAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOCAL_MODE_DISABLED,
    LOCAL_MODE_PREFER_LOCAL,
    UNITS,
    resolve_api_profile,
)
from .control_values import (
    cloud_control_snapshot,
    control_value,
    find_control_value,
    setting_value,
)
from .data_sources import snapshot_with_data_source
from .device_support import (
    get_parameter_sensor_names,
    is_devcode_supported,
    map_sensor_title,
    needs_parameter_fetch,
)
from .sensor_titles import sensor_display_name

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TIME,
    Platform.TEXT,
]
LOCAL_PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Consecutive cloud revisions that may re-read a control value which never
# resolves. Without a bound, a permanently unreadable field would cost one API
# request every refresh for as long as the entry stays loaded.
MAX_CONTROL_VALUE_RETRIES = 3

_LOGGER = logging.getLogger(__name__)


def _normalize_devcode(value: Any) -> int | None:
    """Normalize raw devcode payloads to integers when possible."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DessMonitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug("Setting up DessMonitor integration for entry: %s", entry.entry_id)

    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_CLOUD)
    if connection_type == CONNECTION_TYPE_LOCAL:
        return await _async_setup_local_entry(hass, entry)

    api = _create_api_client(hass, entry)
    local_mode = entry.options.get(CONF_LOCAL_MODE, LOCAL_MODE_DISABLED)
    if local_mode != LOCAL_MODE_PREFER_LOCAL:
        await _authenticate_api_client(api)

    coordinator = await _create_coordinator(hass, entry, api)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("DessMonitor integration setup completed successfully")
    return True


async def _async_setup_local_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a non-blocking, read-only local collector entry."""
    from .local.coordinator import DessMonitorLocalCoordinator

    coordinator = DessMonitorLocalCoordinator(hass, {**entry.data, **entry.options})
    try:
        await coordinator.async_setup()
    except OSError as err:
        _LOGGER.warning("Unable to start local collector services: %s", err)
        raise ConfigEntryNotReady from err

    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, LOCAL_PLATFORMS)
    _LOGGER.info("DessMonitor local mode is ready and waiting for its collector")
    return True


def _create_api_client(hass: HomeAssistant, entry: ConfigEntry) -> DessMonitorAPI:
    """Create API client with storage-backed token handling."""
    username = entry.data["username"]
    company_key = entry.data.get("company_key", "bnrl_frRFjEz8Mkn")
    _LOGGER.debug("Initializing API client for user: %s", username)

    api_profile = resolve_api_profile(entry.data)

    store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_auth")

    return DessMonitorAPI(
        username=username,
        password=entry.data["password"],
        company_key=company_key,
        store=store,
        api_profile=api_profile,
    )


async def _authenticate_api_client(api: DessMonitorAPI) -> None:
    """Authenticate API client while honouring cached credentials."""
    try:
        if await api.load_saved_token():
            _LOGGER.info("Reused saved token for DessMonitor integration")
            return

        await _authenticate_with_token_refresh(api)
    except DessMonitorError as err:
        _LOGGER.warning(
            "DessMonitor authentication failed during setup (will retry): %s", err
        )
        raise ConfigEntryNotReady from err
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.error("Unexpected error during DessMonitor authentication: %s", err)
        _LOGGER.debug("Authentication setup error details", exc_info=True)
        raise ConfigEntryNotReady from err


async def _authenticate_with_token_refresh(api: DessMonitorAPI) -> None:
    """Perform authentication, retrying once with a fresh token if needed."""
    _LOGGER.debug("No valid cached token, performing initial authentication")
    try:
        await api.authenticate()
        _LOGGER.info("Initial authentication successful for DessMonitor integration")
        return
    except DessMonitorError:
        _LOGGER.info(
            "Cached DessMonitor token rejected during initial refresh, requesting a new token"
        )
        await api.clear_saved_token()

    _LOGGER.debug("Retrying authentication after clearing cached token")
    await api.authenticate()
    _LOGGER.info("Fresh authentication successful for DessMonitor integration")


async def _create_coordinator(
    hass: HomeAssistant, entry: ConfigEntry, api: DessMonitorAPI
) -> "DessMonitorDataUpdateCoordinator":
    """Create data coordinator and perform the initial refresh."""
    update_interval = entry.options.get(
        CONF_UPDATE_INTERVAL,
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )
    _LOGGER.debug("Using update interval: %d seconds", update_interval)

    local_mode = entry.options.get(CONF_LOCAL_MODE, LOCAL_MODE_DISABLED)
    setup_local: Callable[[], Awaitable[None]] | None = None
    if local_mode == LOCAL_MODE_PREFER_LOCAL:
        from .local.hybrid import DessMonitorHybridCoordinator

        hybrid_coordinator = DessMonitorHybridCoordinator(
            hass,
            api,
            update_interval,
            {**entry.data, **entry.options},
            entry.entry_id,
            config_entry=entry,
        )
        coordinator: DessMonitorDataUpdateCoordinator = hybrid_coordinator
        setup_local = hybrid_coordinator.async_setup_local
    else:
        coordinator = DessMonitorDataUpdateCoordinator(
            hass,
            api,
            update_interval,
            entry_id=entry.entry_id,
            config_entry=entry,
        )
    _LOGGER.debug("Created data update coordinator, performing first refresh")

    try:
        if setup_local is not None:
            await setup_local()
        else:
            await coordinator.async_setup_cloud_cache()
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("First data refresh completed successfully")
    except DessMonitorError as err:
        await coordinator.async_shutdown()
        _LOGGER.warning(
            "DessMonitor data refresh failed during setup (will retry): %s", err
        )
        raise ConfigEntryNotReady from err
    except Exception as err:  # pylint: disable=broad-except
        await coordinator.async_shutdown()
        _LOGGER.error("Failed to perform initial data refresh: %s", err)
        _LOGGER.debug("Initial refresh error details", exc_info=True)
        raise ConfigEntryNotReady from err

    return coordinator


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading DessMonitor integration entry: %s", entry.entry_id)

    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_CLOUD)
    platforms = (
        LOCAL_PLATFORMS if connection_type == CONNECTION_TYPE_LOCAL else PLATFORMS
    )
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        coordinator = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        _LOGGER.debug("Coordinator removed and platforms unloaded successfully")

        if coordinator is not None and hasattr(coordinator, "async_shutdown"):
            try:
                await coordinator.async_shutdown()
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.warning("Error stopping local collector services: %s", err)
        elif (
            coordinator is not None
            and hasattr(coordinator, "api")
            and hasattr(coordinator.api, "close")
        ):
            try:
                await coordinator.api.close()
                _LOGGER.debug("API session closed successfully")
            except Exception as err:
                _LOGGER.warning("Error closing API session: %s", err)
    else:
        _LOGGER.error("Failed to unload platforms for entry: %s", entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.info("Reloading DessMonitor integration due to configuration changes")
    await hass.config_entries.async_reload(entry.entry_id)


class DessMonitorDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the DessMonitor API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DessMonitorAPI,
        update_interval: int,
        *,
        entry_id: str | None = None,
        allow_cached_fallback: bool = True,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize."""
        self.api = api
        self.ctrl_field_cache: dict[str, dict[str, Any]] = {}
        self.ctrl_value_cache: dict[str, dict[str, str]] = {}
        self._ctrl_locks: dict[str, asyncio.Lock] = {}
        self._ctrl_field_attempts: dict[str, int] = {}
        self._ctrl_value_attempts: dict[str, int] = {}
        self._ctrl_value_retries: dict[str, int] = {}
        self._ctrl_cloud_samples: dict[str, object] = {}
        self.param_cache: dict[str, dict[str, Any]] = {}
        self.cloud_revision = 0
        # Every serial whose payload in the current snapshot was fetched by an
        # earlier cycle rather than this one, whether the refresh failed for
        # that device alone or for the whole account. The hybrid overlay reads
        # it so a retained device is never presented as live.
        self.stale_cloud_serials: frozenset[str] = frozenset()
        self._allow_cached_fallback = allow_cached_fallback
        self._cached_cloud_data: dict[str, Any] = {}
        self._cloud_snapshot_store: Store[dict[str, Any]] | None = (
            Store(hass, 1, f"{DOMAIN}_{entry_id}_cloud_snapshot") if entry_id else None
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
            always_update=False,
        )

    async def async_shutdown(self) -> None:
        """Close the cloud client owned by this coordinator."""
        await super().async_shutdown()
        await self.api.close()

    async def async_setup_cloud_cache(self) -> None:
        """Load the last successful API snapshot before the first refresh."""
        if self._cloud_snapshot_store is None:
            return
        try:
            stored = await self._cloud_snapshot_store.async_load()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Unable to load cached DessMonitor snapshot: %s", err)
            return
        if not isinstance(stored, dict):
            return
        data = stored.get("data")
        if isinstance(data, dict):
            self._cached_cloud_data = data

    async def _async_store_cloud_snapshot(self, data: dict[str, Any]) -> None:
        """Persist a successful API refresh without making telemetry fail."""
        self._cached_cloud_data = data
        if self._cloud_snapshot_store is None:
            return
        try:
            await self._cloud_snapshot_store.async_save({"data": data})
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Unable to save cached DessMonitor snapshot: %s", err)

    def _cached_cloud_fallback(self, err: Exception) -> dict[str, Any] | None:
        """Return an explicitly stale snapshot when API-only continuity is enabled."""
        if not self._allow_cached_fallback or not self._cached_cloud_data:
            return None
        _LOGGER.warning(
            "DessMonitor API refresh failed; retaining the cached cloud snapshot: %s",
            err,
        )
        self.stale_cloud_serials = frozenset(self._cached_cloud_data)
        return snapshot_with_data_source(self._cached_cloud_data, "Cached Cloud")

    async def async_get_controls_with_values(
        self, pn: str, devcode: int, devaddr: int, sn: str
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Get control field definitions and their current values.

        Seed values from the ordinary cloud payload and retry only missing
        values once per cloud revision, until three rounds recover nothing.
        Ordinary telemetry can still recover values after that budget is spent.
        Local pushes cannot trigger retries.
        The per-device lock shares work between select/number/button loaders.
        """
        if sn not in self._ctrl_locks:
            self._ctrl_locks[sn] = asyncio.Lock()

        async with self._ctrl_locks[sn]:
            if not self.ctrl_field_cache.get(sn):
                if self._ctrl_field_attempts.get(sn) == self.cloud_revision:
                    return {}, self.ctrl_value_cache.get(sn, {})
                self._ctrl_field_attempts[sn] = self.cloud_revision
                try:
                    controls = await self.api.get_device_control_fields(
                        pn, devcode, devaddr, sn
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to fetch control fields for device %s: %s",
                        sn,
                        err,
                    )
                    return {}, {}
                self.ctrl_field_cache[sn] = controls

            controls = self.ctrl_field_cache[sn]
            values = self.ctrl_value_cache.setdefault(sn, {})
            before = dict(values)
            self._sync_control_values_from_cloud(sn)
            by_id = {cfg["id"]: cfg for cfg in controls.values() if cfg.get("id")}
            missing = [
                cfg["id"]
                for cfg in controls.values()
                if cfg.get("id")
                and setting_value(cfg, values.get(cfg["id"])) is None
                and not (
                    cfg.get("type") == "options" and len(cfg.get("options", {})) == 1
                )
            ]
            retries = self._ctrl_value_retries.get(sn, 0)
            if (
                missing
                and retries < MAX_CONTROL_VALUE_RETRIES
                and self._ctrl_value_attempts.get(sn) != self.cloud_revision
            ):
                self._ctrl_value_attempts[sn] = self.cloud_revision
                fetched = await self._fetch_all_control_values(
                    pn, devcode, devaddr, sn, missing
                )
                # A cloud refresh or accepted write may have filled a value
                # while these reads were in flight. Do not overwrite it.
                for field_id, value in fetched.items():
                    normalized = setting_value(by_id[field_id], value)
                    if (
                        normalized is not None
                        and setting_value(by_id[field_id], values.get(field_id)) is None
                    ):
                        values[field_id] = normalized
                self._sync_control_values_from_cloud(sn)
                # Spend the budget only on rounds that recovered nothing, so a
                # device still making progress keeps retrying the remainder.
                if any(
                    setting_value(by_id[field_id], values.get(field_id)) is not None
                    for field_id in missing
                ):
                    self._ctrl_value_retries[sn] = 0
                else:
                    self._ctrl_value_retries[sn] = retries + 1
                    if self._ctrl_value_retries[sn] == MAX_CONTROL_VALUE_RETRIES:
                        _LOGGER.info(
                            "Giving up on %d unreadable control value(s) for device "
                            "%s after %d attempts; ordinary cloud telemetry still "
                            "updates them, and reloading the entry retries",
                            len(missing),
                            sn,
                            MAX_CONTROL_VALUE_RETRIES,
                        )
            changed = values != before
        if changed:
            # Existing entities also need to see late read recovery. Preserve
            # the independent cloud refresh timer and revision counter.
            self.async_update_listeners()
        return controls, values

    def _sync_control_values_from_cloud(self, sn: str) -> None:
        """Refresh exact settings only when a new cloud sample arrives."""
        stamp, points = cloud_control_snapshot(self, sn)
        if self._ctrl_cloud_samples.get(sn) == stamp:
            return
        controls = self.ctrl_field_cache.get(sn, {})
        if not controls:
            return
        self._ctrl_cloud_samples[sn] = stamp
        values = self.ctrl_value_cache.setdefault(sn, {})
        for name, config in controls.items():
            field_id = config.get("id")
            value = setting_value(config, find_control_value(points, name))
            if field_id and value is not None:
                values[field_id] = value

    async def _fetch_all_control_values(
        self,
        pn: str,
        devcode: int,
        devaddr: int,
        sn: str,
        field_ids: list[str],
    ) -> dict[str, str]:
        """Fetch current values for all control fields in parallel."""
        if not field_ids:
            return {}

        sem = asyncio.Semaphore(5)

        async def _fetch_one(field_id: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    result = await self.api.get_device_control_value(
                        pn, devcode, devaddr, sn, field_id
                    )
                    return field_id, control_value(result.get("val"))
                except Exception as err:
                    _LOGGER.debug(
                        "Failed to read control value %s for %s: %s",
                        field_id,
                        sn,
                        err,
                    )
                    return field_id, None

        _LOGGER.info("Fetching %d control values for device %s", len(field_ids), sn)
        results = await asyncio.gather(*[_fetch_one(fid) for fid in field_ids])
        values = {fid: val for fid, val in results if val is not None}
        _LOGGER.info(
            "Fetched %d/%d control values for device %s",
            len(values),
            len(field_ids),
            sn,
        )
        return values

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Starting data update cycle")
        try:
            self.stale_cloud_serials = frozenset()
            collectors = await self._fetch_collectors()
            data = await self._gather_all_device_data(collectors)
            await self._merge_summary_data(data, bool(collectors))

            _LOGGER.info(
                "Data update completed successfully: %d devices total (%d retained)",
                len(data),
                len(self.stale_cloud_serials),
            )
            await self._async_store_cloud_snapshot(data)
            self.cloud_revision += 1
            for sn in self.ctrl_field_cache:
                self._sync_control_values_from_cloud(sn)
            return snapshot_with_data_source(
                data, "Cloud", stale=self.stale_cloud_serials
            )
        except UpdateFailed as err:
            if cached := self._cached_cloud_fallback(err):
                return cached
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "Error communicating with DessMonitor API during update: %s", err
            )
            _LOGGER.debug("Data update error details", exc_info=True)
            update_error = UpdateFailed(
                f"Error communicating with DessMonitor API: {err}"
            )
            if cached := self._cached_cloud_fallback(update_error):
                return cached
            raise update_error from err

    async def _fetch_collectors(self) -> list[dict[str, Any]]:
        """Fetch each physical collector once even if it belongs to two projects."""
        _LOGGER.debug("Fetching collectors list")
        collectors, _projects = await self.api.get_collectors()
        # Device queries use PN, not project ID. Keep the last occurrence's
        # metadata, as the previous per-project data.update() loop did.
        unique = {collector["pn"]: collector for collector in collectors}
        _LOGGER.debug(
            "Found %d unique collectors to process from %d API rows",
            len(unique),
            len(collectors),
        )
        return list(unique.values())

    async def _gather_all_device_data(
        self, collectors: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Collect last known data for all devices.

        A device the API fails on this cycle keeps the payload an earlier cycle
        fetched, so a single slow request cannot make a whole inverter's
        entities unavailable while the rest of the account refreshes normally
        (#54, #55). A device the API no longer lists is genuinely gone and is
        dropped. When nothing fresh arrives at all, the error is raised so the
        cached-cloud fallback and the hybrid local overlay take over instead of
        a successful-looking empty snapshot replacing the stored one.
        """
        if not collectors and self._cached_cloud_data:
            raise UpdateFailed(
                "Collector list came back empty while devices are known; "
                "treating it as a failed refresh"
            )

        data: dict[str, Any] = {}
        errors: list[str] = []
        failed_serials: set[str] = set()

        for index, collector in enumerate(collectors, start=1):
            collector_id = collector["pn"]
            _LOGGER.debug(
                "Processing collector %d/%d: %s",
                index,
                len(collectors),
                collector_id,
            )

            try:
                collector_devices, failures = await self._fetch_devices_for_collector(
                    collector
                )
            except DessMonitorError as err:
                _LOGGER.warning("Skipping collector %s: %s", collector_id, err)
                errors.append(f"{collector_id}: {err}")
                failed_serials.update(self._cached_serials_for_collector(collector_id))
                continue

            data.update(collector_devices)
            for device_sn, message in failures.items():
                errors.append(f"{device_sn}: {message}")
                failed_serials.add(device_sn)

        if not data and errors:
            raise UpdateFailed(f"Cloud refresh failed: {'; '.join(errors)}")

        retained = self._retain_failed_devices(failed_serials, data)
        if retained:
            self.stale_cloud_serials = frozenset(retained)
            data.update(retained)

        return data

    def _cached_serials_for_collector(self, collector_id: str) -> set[str]:
        """Return the stored serials that belong to one collector."""
        return {
            device_sn
            for device_sn, payload in self._cached_cloud_data.items()
            if isinstance(payload, dict)
            and str(payload.get("collector", {}).get("pn", "")) == collector_id
        }

    def _retain_failed_devices(
        self, failed_serials: set[str], fresh: dict[str, Any]
    ) -> dict[str, Any]:
        """Return the stored payload for each device that failed this cycle."""
        retained: dict[str, Any] = {}
        for device_sn in sorted(failed_serials - set(fresh)):
            cached = self._cached_cloud_data.get(device_sn)
            if not isinstance(cached, dict):
                continue
            retained[device_sn] = copy.deepcopy(cached)

        if retained:
            _LOGGER.warning(
                "Retaining the last known cloud payload for %d device(s) that "
                "failed this refresh: %s",
                len(retained),
                ", ".join(retained),
            )
        return retained

    async def _fetch_devices_for_collector(
        self, collector: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Fetch data for all devices under a collector.

        Returns the devices that answered and the error reported for each
        device that did not, so the caller can retain its last known payload.
        """
        collector_id = collector["pn"]
        devices_response = await self.api.get_collector_devices(collector_id)
        device_list = devices_response.get("dev", [])
        _LOGGER.debug("Collector %s has %d devices", collector_id, len(device_list))

        device_data: dict[str, Any] = {}
        failures: dict[str, str] = {}
        for index, device in enumerate(device_list, start=1):
            device_sn = device["sn"]
            devcode = _normalize_devcode(device.get("devcode"))
            _LOGGER.debug(
                "Processing device %d/%d: %s (devcode=%s, devaddr=%s)",
                index,
                len(device_list),
                device_sn,
                device["devcode"],
                device["devaddr"],
            )

            try:
                last_data = await self._fetch_device_data(collector_id, device, devcode)
            except DessMonitorError as err:
                _LOGGER.warning(
                    "Device %s (collector %s) did not answer: %s",
                    device_sn,
                    collector_id,
                    err,
                )
                failures[device_sn] = str(err)
                continue

            device_data[device_sn] = {
                "collector": collector,
                "device": device,
                "data": last_data,
            }

        return device_data, failures

    async def _fetch_device_data(
        self,
        collector_id: str,
        device: dict[str, Any],
        devcode: int | None,
    ) -> list[dict[str, Any]]:
        """Fetch latest datapoints for a single device.

        When the devcode declares ``parameter_sensor_names``, the parameters
        endpoint is queried in parallel and matching entries are merged into
        the result so that sensors like *Battery percentage* (SOC) become
        available even though they are absent from ``queryDeviceLastData``.
        """
        device_sn = device["sn"]

        if devcode is not None and needs_parameter_fetch(devcode):
            last_data, param_points = await asyncio.gather(
                self.api.get_device_last_data(
                    pn=collector_id,
                    devcode=device["devcode"],
                    devaddr=device["devaddr"],
                    sn=device_sn,
                ),
                self._fetch_device_parameter_data(collector_id, device, devcode),
            )
            self._merge_parameter_data(last_data, param_points, devcode, device_sn)
        else:
            last_data = await self.api.get_device_last_data(
                pn=collector_id,
                devcode=device["devcode"],
                devaddr=device["devaddr"],
                sn=device_sn,
            )

        _LOGGER.debug(
            "Stored data for device %s with %d data points",
            device_sn,
            len(last_data),
        )
        return last_data

    async def _fetch_device_parameter_data(
        self,
        collector_id: str,
        device: dict[str, Any],
        devcode: int,
    ) -> list[dict[str, Any]]:
        """Fetch parameter data and convert wanted entries to data-point format.

        Returns an empty list on error so that a failure here never blocks
        the primary data fetch.
        """
        wanted_names = get_parameter_sensor_names(devcode)
        try:
            params = await self.api.get_device_parameters(
                pn=collector_id,
                devcode=device["devcode"],
                devaddr=device["devaddr"],
                sn=device["sn"],
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Failed to fetch parameter data for device %s: %s",
                device["sn"],
                err,
            )
            return []

        points: list[dict[str, Any]] = []
        for name, info in params.items():
            if name in wanted_names:
                points.append(
                    {
                        "title": name,
                        "val": info.get("value", ""),
                        "unit": info.get("unit", ""),
                    }
                )
        return points

    def _merge_parameter_data(
        self,
        last_data: list[dict[str, Any]],
        param_points: list[dict[str, Any]],
        devcode: int,
        device_sn: str,
    ) -> None:
        """Merge parameter-sourced data points into *last_data* (in place).

        Duplicates are detected by checking both the raw title and its
        devcode-mapped variant, matching the logic used in
        ``_merge_summary_data``.
        """
        if not param_points:
            return

        existing_titles: set[str] = set()
        for point in last_data:
            title = point.get("title")
            if title:
                existing_titles.add(title)
        mapped_titles: set[str] = {
            map_sensor_title(devcode, title) for title in existing_titles if title
        }
        existing_titles.update(mapped_titles)

        merged: list[str] = []
        for point in param_points:
            title = point.get("title", "")
            mapped = map_sensor_title(devcode, title)
            if title not in existing_titles and mapped not in existing_titles:
                last_data.append(point)
                existing_titles.add(title)
                existing_titles.add(mapped)
                merged.append(title)

        if merged:
            _LOGGER.debug(
                "Merged %d parameter sensors (%s) for device %s",
                len(merged),
                ", ".join(merged),
                device_sn,
            )

    async def _merge_summary_data(
        self, data: dict[str, Any], collectors_present: bool
    ) -> None:
        """Merge summary dashboard data into the regular payload."""
        if not collectors_present:
            return

        summary_data = await self._fetch_summary_payload()
        if not summary_data:
            return

        for device_sn, device_info in data.items():
            summary_points = summary_data.get(device_sn, {}).get("data", [])
            if not summary_points:
                continue

            device_meta = device_info.get("device", {})
            devcode = _normalize_devcode(device_meta.get("devcode"))
            devcode_supported = devcode is not None and is_devcode_supported(devcode)

            existing_data = device_info["data"]
            existing_titles = {
                point.get("title") for point in existing_data if point.get("title")
            }

            # Also track mapped titles so "Today generation" and "energyToday"
            # are treated as the same sensor and avoid duplicate entity warnings.
            mapped_titles: set[str | None] = set()
            if devcode_supported and devcode is not None:
                mapped_titles = {
                    map_sensor_title(devcode, title)
                    for title in existing_titles
                    if title
                }
            existing_titles.update({title for title in mapped_titles if title})

            # Comparing titles alone is not enough: a summary field and a mapped
            # reading can be separate sensor keys that publish the same entity
            # name, such as "energyToday" beside "Energy Today". A device that
            # reports both then gets two entities with one name, and the one the
            # summary feeds reads zero wherever the vendor leaves that field
            # unset (#58).
            existing_names = {
                name
                for name in (
                    sensor_display_name(str(title))
                    for title in existing_titles
                    if title
                )
                if name
            }

            unique_summary_points = [
                point
                for point in summary_points
                if point.get("title")
                and point.get("title") not in existing_titles
                and sensor_display_name(str(point.get("title"))) not in existing_names
                and (
                    not devcode_supported
                    or devcode is None
                    or map_sensor_title(devcode, point.get("title"))
                    not in existing_titles
                )
            ]

            if not unique_summary_points:
                _LOGGER.debug(
                    "Skipping summary merge for %s (%s) because all titles already exist",
                    device_info.get("device", {}).get("alias", "Unknown"),
                    device_sn,
                )
                continue

            existing_data.extend(unique_summary_points)
            existing_titles.update(
                point.get("title") for point in unique_summary_points
            )

            device_alias = device_info.get("device", {}).get("alias", "Unknown")
            summary_types = [point.get("title") for point in unique_summary_points]
            _LOGGER.debug(
                "Merged %d summary sensors (%s) for %s (%s)",
                len(unique_summary_points),
                ", ".join(summary_types),
                device_alias,
                device_sn,
            )

    async def _fetch_summary_payload(self) -> dict[str, Any] | None:
        """Fetch summary data for dashboard sensors."""
        try:
            _LOGGER.debug("Fetching project information for summary data")
            projects_response = await self.api._make_request(
                "queryPlants", {"pagesize": 1}
            )

            plants = projects_response.get("dat", {}).get("plant")
            if not plants:
                _LOGGER.warning("No projects found for summary data")
                return None

            project_id = plants[0]["pid"]
            _LOGGER.debug("Using project ID %s for summary data", project_id)

            summary_data = await self.api.get_device_summary_data(project_id)
            _LOGGER.debug("Retrieved summary data for %d devices", len(summary_data))
            return summary_data
        except KeyError:
            _LOGGER.warning("Failed to get project information for summary data")
            return None
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to fetch summary data: %s", err)
            return None


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> dict:
    """Return diagnostics for a device entry."""
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_sn = _resolve_device_sn(device)
    if not device_sn or device_sn not in coordinator.data:
        return {"error": "Device not found"}

    device_info = coordinator.data[device_sn]
    device_data = device_info.get("data", [])

    diagnostics = _build_base_diagnostics(device_sn, device_info, len(device_data))

    config_values, status_values = _categorize_device_data(device_data)
    diagnostics["configuration"].update(config_values)
    diagnostics["status"].update(status_values)

    (
        control_config,
        device_parameters,
        control_error,
    ) = await _fetch_control_details(coordinator, device_sn, device_info, device_data)

    diagnostics["configuration"].update(control_config)
    if device_parameters:
        diagnostics["parameters"] = device_parameters
    if control_error:
        diagnostics["battery_config_error"] = control_error

    diagnostics["summary"] = _build_diagnostics_summary(
        coordinator, device_data, diagnostics
    )

    _LOGGER.debug(
        "Generated diagnostics for device %s with %d config items",
        device_sn,
        len(diagnostics["configuration"]),
    )

    return diagnostics


def _resolve_device_sn(device: dr.DeviceEntry) -> str | None:
    """Extract DessMonitor serial number from device identifiers."""
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            return identifier
    return None


def _build_base_diagnostics(
    device_sn: str, device_info: dict[str, Any], datapoint_count: int
) -> dict[str, Any]:
    """Return the base diagnostics structure for a device."""
    device_meta = device_info.get("device", {})
    collector_meta = device_info.get("collector", {})

    return {
        "device_info": {
            "serial_number": device_sn,
            "alias": device_meta.get("alias", "Unknown"),
            "firmware_version": collector_meta.get("fireware", "Unknown"),
            "collector_pn": collector_meta.get("pn", "Unknown"),
            "device_code": device_meta.get("devcode"),
            "device_address": device_meta.get("devaddr"),
        },
        "configuration": {},
        "status": {},
        "raw_data_points": datapoint_count,
    }


CONFIG_KEYWORDS = {
    "setting",
    "priority",
    "voltage setting",
    "cutoff",
    "capacity",
    "type",
    "configuration",
}
STATUS_KEYWORDS = {"status", "operating mode", "state", "online", "connectivity"}
PRIORITY_MAPPINGS = {
    "Output priority": {"SBU": 2, "UTI": 0, "SOL": 1, "SUB": 3},
    "Charger Source Priority": {
        "PV FIRST": 1,
        "UTILITY FIRST": 0,
        "PV_UTILITY": 2,
        "PV ONLY": 3,
    },
}


def _categorize_device_data(
    device_data: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split raw device data into configuration and status dictionaries."""
    configuration: dict[str, Any] = {}
    status: dict[str, Any] = {}

    for data_point in device_data:
        title = data_point.get("title", "")
        value = data_point.get("val")
        unit = data_point.get("unit", "")

        normalized_title = title.lower()
        if normalized_title in {"output priority", "charger source priority"} or any(
            keyword in normalized_title for keyword in CONFIG_KEYWORDS
        ):
            configuration[title] = {"value": value, "unit": unit}
        elif any(keyword in normalized_title for keyword in STATUS_KEYWORDS):
            status[title] = {"value": value, "unit": unit}

    return configuration, status


async def _fetch_control_details(
    coordinator: DessMonitorDataUpdateCoordinator,
    device_sn: str,
    device_info: dict[str, Any],
    device_data: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """Fetch control fields and parameters for diagnostics."""
    collector_meta = device_info.get("collector", {})
    device_meta = device_info.get("device", {})

    try:
        _LOGGER.debug("Fetching control fields and parameters for device %s", device_sn)
        control_fields = await coordinator.api.get_device_control_fields(
            pn=collector_meta.get("pn"),
            devcode=device_meta.get("devcode"),
            devaddr=device_meta.get("devaddr"),
            sn=device_sn,
        )
        device_parameters = await coordinator.api.get_device_parameters(
            pn=collector_meta.get("pn"),
            devcode=device_meta.get("devcode"),
            devaddr=device_meta.get("devaddr"),
            sn=device_sn,
        )
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Failed to fetch control fields/parameters for device %s: %s",
            device_sn,
            err,
        )
        return {}, {}, str(err)

    formatted_fields = _format_control_fields(control_fields, device_data)
    _LOGGER.debug(
        "Added %d control fields and %d parameters to diagnostics for device %s",
        len(formatted_fields),
        len(device_parameters),
        device_sn,
    )
    return formatted_fields, device_parameters, None


def _format_control_fields(
    control_fields: dict[str, Any], device_data: list[dict[str, Any]]
) -> dict[str, Any]:
    """Format control field metadata for diagnostics output."""
    formatted: dict[str, Any] = {}

    for field_name, field_data in control_fields.items():
        if field_data.get("type") == "options":
            formatted[field_name] = _format_option_field(
                field_name, field_data, device_data
            )
        else:
            formatted[field_name] = _format_numeric_field(
                field_name, field_data, device_data
            )

    return formatted


def _format_option_field(
    field_name: str, field_data: dict[str, Any], device_data: list[dict[str, Any]]
) -> dict[str, Any]:
    """Format control fields that expose selectable options."""
    sensor_value = _extract_sensor_value(device_data, field_name)
    current_value = _resolve_option_value(
        field_name, field_data, sensor_value, device_data
    )

    options_display = [
        f"{opt['key']}: {opt['val']}" for opt in field_data.get("options", [])
    ]

    return {
        "value": current_value,
        "unit": "",
        "options": options_display,
        "id": field_data.get("id"),
    }


def _format_numeric_field(
    field_name: str,
    field_data: dict[str, Any],
    device_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Format numeric control fields, reporting only what was read."""
    current_value = _extract_sensor_value(device_data, field_name, default="Not Set")

    unit = ""
    if "Voltage" in field_name:
        unit = UNITS["VOLTAGE"]
    elif "Current" in field_name:
        unit = UNITS["CURRENT"]

    return {
        "value": current_value,
        "unit": unit,
        "id": field_data.get("id"),
    }


def _resolve_option_value(
    field_name: str,
    field_data: dict[str, Any],
    sensor_value: Any,
    device_data: list[dict[str, Any]],
):
    """Resolve option value with priority mappings when available."""
    if sensor_value and field_name in PRIORITY_MAPPINGS:
        desired_key = _match_priority_option(field_name, str(sensor_value))
        if desired_key is not None:
            return _lookup_option_value(field_data, desired_key)

    if sensor_value:
        return sensor_value

    if field_name == "Output Voltage":
        output_voltage = _extract_sensor_value(device_data, "Output Voltage")
        if output_voltage is not None:
            try:
                voltage_key = str(float(output_voltage))
            except (TypeError, ValueError):
                voltage_key = str(output_voltage)
            return _lookup_option_value(
                field_data,
                voltage_key,
                fallback=f"{output_voltage} V (Custom)",
            )

    return "Not Set"


def _match_priority_option(field_name: str, sensor_value: str) -> str | None:
    """Match a human-readable sensor value to its option key."""
    options = PRIORITY_MAPPINGS.get(field_name, {})
    for option_text, option_key in options.items():
        if sensor_value.upper() == option_text.upper():
            return str(option_key)
    return None


def _lookup_option_value(
    field_data: dict[str, Any], option_key: str, fallback: str | None = None
) -> str:
    """Return display value for a control option key."""
    for option in field_data.get("options", []):
        if option.get("key") == option_key:
            return option.get("val", option_key)
    return fallback or option_key


def _extract_sensor_value(
    device_data: list[dict[str, Any]], field_name: str, default: Any | None = None
) -> Any:
    """Pull matching sensor value from the latest device data."""
    for data_point in device_data:
        if data_point.get("title") == field_name:
            return data_point.get("val")
    return default


def _build_diagnostics_summary(
    coordinator: DessMonitorDataUpdateCoordinator,
    device_data: list[dict[str, Any]],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Create diagnostics summary block."""
    sensor_types = coordinator.data.get("sensor_types", [])
    total_sensors = 0
    if isinstance(sensor_types, list):
        total_sensors = len(
            [dp for dp in device_data if dp.get("title") in sensor_types]
        )

    last_update = _extract_sensor_value(device_data, "Timestamp", "Unknown")

    return {
        "total_sensors_created": total_sensors,
        "last_update": last_update,
        "control_fields_found": len(diagnostics.get("configuration", {})),
        "parameters_found": len(diagnostics.get("parameters", {})),
        "unique_features": [
            "39 Control Fields (vs ~10 in other projects)",
            "Battery EQ Mode settings",
            "Advanced power saving modes",
            "Comprehensive voltage protection settings",
            "Detailed buzzer and display controls",
            "Remote boot control options",
        ],
    }
