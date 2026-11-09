"""The DessMonitor integration."""

from __future__ import annotations

import asyncio
import copy
import ipaddress
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta

# Bound directly: this package has a time.py platform module, and importing
# it rebinds the name `time` in this module's namespace.
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DessMonitorAPI, DessMonitorError
from .const import (
    CONF_API_PROFILE,
    CONF_COMPANY_KEY,
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_COLLECTOR_IPS,
    CONF_LOCAL_DEVICE_ADDRESS,
    CONF_LOCAL_DEVICE_CODE,
    CONF_LOCAL_EXPECTED_PN,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_MODE,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_REDIRECT_CONFIRMED,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_LOCAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOCAL_MODE_DISABLED,
    LOCAL_MODE_PREFER_LOCAL,
    UNITS,
    VERSION,
    resolve_api_profile,
)
from .control_values import (
    cloud_control_snapshot,
    control_value,
    find_control_value,
    first_control_value,
    option_key_for,
    setting_value,
)
from .data_sources import snapshot_with_data_source
from .device_support import (
    control_value_reading,
    get_parameter_sensor_names,
    is_devcode_supported,
    map_sensor_title,
    needs_parameter_fetch,
)
from .sensor_titles import sensor_display_name
from .support_report import PARTIAL as SUPPORT_PARTIAL
from .support_report import SUPPORTED as SUPPORT_SUPPORTED
from .support_report import UNSUPPORTED as SUPPORT_UNSUPPORTED
from .support_report import (
    build_support_report,
    device_support_status,
    is_attribute_reading,
    report_checksum,
    resolved_key_for,
    short_identity,
)

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

# The same bound for rounds the vendor never answered. A field the API answers
# with nothing is one this hardware does not carry, and three rounds settle it.
# A read that times out says nothing about the field: on the hardware in #60 a
# field that timed out answered on a later round, and spending the short budget
# on those rounds left a readable control reading unknown until the entry was
# reloaded. These rounds get a longer budget so flaky reads can recover, still
# bounded so a dead API cannot be polled for the life of the entry.
MAX_UNANSWERED_CONTROL_VALUE_RETRIES = 12

# Consecutive cloud revisions that may re-ask for a device's control field
# list. A grid-tie collector has no control template at all and the platform
# answers `queryDeviceCtrlField` with ERR_NO_RECORD every time (#62), so
# without a bound that device costs one failing request and one warning per
# refresh for the life of the entry. The budget matches the unanswered value
# reads: long enough for a flaky account to recover, short enough to settle.
MAX_CONTROL_FIELD_RETRIES = 12

# Wall clock one round of control-value reads may take. The API answers each
# field separately and a stalled field costs the full request timeout, so a
# round of dozens of fields can outlive Home Assistant's startup window and
# leave every control on the account unavailable meanwhile. Reads still in
# flight at the deadline are abandoned and retried on a later revision.
CONTROL_VALUE_ROUND_TIMEOUT_SECONDS = 60

# A control value only ever reached the cache once: the retry rounds read the
# fields that have no value, and ordinary telemetry refreshes only the ones a
# collector repeats among its readings. A setting changed in the vendor app or
# on the inverter's own panel therefore stayed as this integration first read
# it for the life of the config entry, which is how the account in #53 came to
# show Back To Grid Voltage at 46 V against the app's 48 and Max Charging
# Current at 40 A against 100.
#
# Re-reading is not free: each field is a separate request that reaches the
# inverter live, over the same single-transaction collector link local mode
# occupies, and a burst of them is what left every control on an account
# unavailable in #61. So a round reads at most CONTROL_VALUE_REFRESH_PER_ROUND
# fields however many a device has, and that cap is the whole cost guarantee.
#
# Which fields those are is learned rather than configured, because a control
# is not necessarily a setting somebody chose. The inverter in #53 negotiates
# Max Charging Current with the battery BMS and moves it on its own, while the
# forty settings around it change perhaps twice a year. Each field therefore
# carries its own interval: a read that finds a new value drops it to
# CONTROL_VALUE_REFRESH_FAST_INTERVAL_SECONDS, a read that finds the same
# value doubles it up to CONTROL_VALUE_REFRESH_MAX_INTERVAL_SECONDS, and a
# round spends its reads on whichever fields are furthest past their own
# interval. A field nobody touches settles at one read a day; one the hardware
# moves is followed within a cloud refresh or two; neither can raise the cost
# of a round, and a field starved by a busier neighbour overtakes it as its
# own ratio climbs.
CONTROL_VALUE_REFRESH_PER_ROUND = 2
CONTROL_VALUE_REFRESH_BASE_INTERVAL_SECONDS = 1800
CONTROL_VALUE_REFRESH_FAST_INTERVAL_SECONDS = 300
CONTROL_VALUE_REFRESH_MAX_INTERVAL_SECONDS = 86400

# How long after Home Assistant writes a setting its own value is trusted
# without being read back. An accepted write is not proof the inverter applied
# it, but reading the field back before the inverter has acted on it would
# bounce the entity to the old value and back for no reason.
CONTROL_VALUE_WRITE_GRACE_SECONDS = 300

_LOGGER = logging.getLogger(__name__)

_SUPPORT_ISSUE_PREFIX = "devcode_support_"
_SUPPORT_LEARN_MORE_URL = (
    "https://github.com/andreas-glaser/ha-dessmonitor/blob/main/"
    "docs/ADDING_DEVCODES.md#request-support"
)


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
        # Values the API answered a control read with that none of that
        # control's own options matches. They are not values the entities can
        # show, and they are not an absence either.
        self.ctrl_unmatched_values: dict[str, dict[str, str]] = {}
        self._ctrl_locks: dict[str, asyncio.Lock] = {}
        self._ctrl_field_attempts: dict[str, int] = {}
        self._ctrl_field_failures: dict[str, int] = {}
        self._ctrl_value_attempts: dict[str, int] = {}
        self._ctrl_value_retries: dict[str, int] = {}
        self._ctrl_value_unanswered: dict[str, bool] = {}
        self._ctrl_cloud_samples: dict[str, object] = {}
        # When each field was last read explicitly, and when Home Assistant
        # last wrote it, both on the monotonic clock. The refresh rotation
        # orders by the first and holds off on the second.
        # A missing entry means never, not long ago: the monotonic clock counts
        # from boot, so a default of 0.0 would make every field look freshly
        # read and freshly written for the host's first half hour.
        self._ctrl_value_read_at: dict[tuple[str, str], float] = {}
        self._ctrl_write_at: dict[tuple[str, str], float] = {}
        # How long each field has earned between reads, by how often reading
        # it has found anything new.
        self._ctrl_refresh_interval: dict[tuple[str, str], float] = {}
        # Fields ordinary telemetry carries for this device. They refresh for
        # free on every cloud sample, so re-reading them buys nothing.
        self._ctrl_cloud_refreshed: dict[str, set[str]] = {}
        self.param_cache: dict[str, dict[str, Any]] = {}
        self.cloud_revision = 0
        # Every serial whose payload in the current snapshot was fetched by an
        # earlier cycle rather than this one, whether the refresh failed for
        # that device alone or for the whole account. The hybrid overlay reads
        # it so a retained device is never presented as live.
        self.stale_cloud_serials: frozenset[str] = frozenset()
        # Devcodes this entry has raised a support card for, so one that
        # stops applying is withdrawn rather than left on screen.
        self._support_issues: set[int] = set()
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

    def _async_update_support_issues(self, data: dict[str, Any]) -> None:
        """Raise one Repairs card per devcode whose readings are not all mapped.

        The answer to "is my inverter supported" was a log line warned once per
        devcode, which nobody reads, and the partial case warned nothing at all
        (#60). One card per devcode, not per device: a five-inverter account of
        one model would otherwise show five identical cards.

        This runs after a successful cloud refresh, never inside
        ``apply_devcode_transformations``, which is a per-reading hot path, and
        it touches no revision counter, so entity discovery is unaffected.
        """
        if self.config_entry is None:
            return

        worst: dict[int, dict[str, Any]] = {}
        evaluated: set[int] = set()
        for payload in data.values():
            raw_devcode = payload.get("device", {}).get("devcode")
            try:
                devcode = int(raw_devcode)
            except (TypeError, ValueError):
                continue
            evaluated.add(devcode)
            support = device_support_status(raw_devcode, payload.get("data", []))
            if support["status"] == SUPPORT_SUPPORTED:
                continue
            previous = worst.get(devcode)
            if previous is None or (
                previous["status"] == SUPPORT_PARTIAL
                and support["status"] == SUPPORT_UNSUPPORTED
            ):
                worst[devcode] = support

        # Every devcode evaluated here, not only those this instance raised a
        # card for: reloading the entry builds a new coordinator with an empty
        # set while the card a previous one raised is still registered, so a
        # devcode that an update has since taught us to map would keep a card
        # saying it is not supported. Deleting an issue that does not exist is
        # a no-op, so the wider sweep costs nothing.
        stale = (self._support_issues | evaluated) - set(worst)
        for devcode in stale:
            ir.async_delete_issue(
                self.hass, DOMAIN, f"{_SUPPORT_ISSUE_PREFIX}{devcode}"
            )
        self._support_issues -= stale

        for devcode, support in worst.items():
            dropped = len(support["unresolved_with_unit"])
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{_SUPPORT_ISSUE_PREFIX}{devcode}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=(
                    "devcode_unsupported"
                    if support["status"] == SUPPORT_UNSUPPORTED
                    else "devcode_partial"
                ),
                translation_placeholders={
                    "devcode": str(devcode),
                    "dropped": str(dropped),
                    "resolved": str(support["resolved"]),
                    "total": str(support["total"]),
                },
                learn_more_url=_SUPPORT_LEARN_MORE_URL,
            )
            self._support_issues.add(devcode)

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

    async def _async_cache_control_fields(
        self, pn: str, devcode: int, devaddr: int, sn: str
    ) -> bool:
        """Fetch a device's control field list once, and say whether it is cached.

        One attempt per cloud revision, and a bounded number of them: a
        grid-tie collector has no control template and the platform refuses the
        request every time (#62), which otherwise costs a failing request and a
        warning on every refresh for as long as the entry stays loaded.
        """
        if self._ctrl_field_attempts.get(sn) == self.cloud_revision:
            return False
        failures = self._ctrl_field_failures.get(sn, 0)
        if failures >= MAX_CONTROL_FIELD_RETRIES:
            return False

        self._ctrl_field_attempts[sn] = self.cloud_revision
        try:
            controls = await self.api.get_device_control_fields(
                pn, devcode, devaddr, sn
            )
        except Exception as err:  # pylint: disable=broad-except
            self._ctrl_field_failures[sn] = failures + 1
            if failures + 1 >= MAX_CONTROL_FIELD_RETRIES:
                _LOGGER.warning(
                    "Giving up on control fields for device %s after %d attempts; "
                    "it publishes no controls until the entry is reloaded: %s",
                    sn,
                    failures + 1,
                    err,
                )
            else:
                # Once at warning level, then quietly: the first line says a
                # device has no controls yet, the rest only repeat it.
                _LOGGER.log(
                    logging.WARNING if not failures else logging.DEBUG,
                    "Failed to fetch control fields for device %s: %s",
                    sn,
                    err,
                )
            return False

        self._ctrl_field_failures.pop(sn, None)
        self.ctrl_field_cache[sn] = controls
        # A fresh field list may offer options the old one did not, so what
        # matched nothing under the previous list says nothing under this one.
        self.ctrl_unmatched_values.pop(sn, None)
        return True

    async def async_get_controls_with_values(
        self, pn: str, devcode: int, devaddr: int, sn: str
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Get control field definitions and their current values.

        Seed values from the ordinary cloud payload and retry only missing
        values once per cloud revision, until three rounds recover nothing.
        Ordinary telemetry can still recover values after that budget is spent.
        Local pushes cannot trigger retries. The field list itself is fetched
        once and then cached whether or not it holds anything, and a device the
        API keeps refusing it for is retired after
        ``MAX_CONTROL_FIELD_RETRIES`` revisions.
        The per-device lock shares work between select/number/button loaders.
        """
        if sn not in self._ctrl_locks:
            self._ctrl_locks[sn] = asyncio.Lock()

        async with self._ctrl_locks[sn]:
            # Presence, not truth: a device the API answers with an empty field
            # list carries no controls, and re-asking every revision for the
            # life of the entry buys nothing.
            if sn not in self.ctrl_field_cache:
                if not await self._async_cache_control_fields(pn, devcode, devaddr, sn):
                    return {}, self.ctrl_value_cache.get(sn, {})

            controls = self.ctrl_field_cache[sn]
            values = self.ctrl_value_cache.setdefault(sn, {})
            before = dict(values)
            self._sync_control_values_from_cloud(sn)
            by_id = {cfg["id"]: cfg for cfg in controls.values() if cfg.get("id")}
            unmatched = self.ctrl_unmatched_values.setdefault(sn, {})
            missing = [
                cfg["id"]
                for cfg in controls.values()
                if cfg.get("id") and setting_value(cfg, values.get(cfg["id"])) is None
                # The API already answered this one with a value none of its
                # options matches. The option list is fixed, so asking again
                # spends the whole budget on a question already answered.
                and cfg["id"] not in unmatched
                and not (
                    cfg.get("type") == "options" and len(cfg.get("options", {})) == 1
                )
            ]
            retries = self._ctrl_value_retries.get(sn, 0)
            budget = self._control_value_budget(sn)
            if (
                missing
                and retries < budget
                and self._ctrl_value_attempts.get(sn) != self.cloud_revision
            ):
                self._ctrl_value_attempts[sn] = self.cloud_revision
                fetched, unanswered = await self._fetch_all_control_values(
                    pn, devcode, devaddr, sn, missing
                )
                self._ctrl_value_unanswered[sn] = unanswered
                # A cloud refresh or accepted write may have filled a value
                # while these reads were in flight. Do not overwrite it.
                for field_id, value in fetched.items():
                    normalized = setting_value(by_id[field_id], value)
                    if normalized is None:
                        # Read, and the answer is outside what this control
                        # offers. Discarding it silently reported the field as
                        # never read and re-read it for the whole budget, while
                        # the log counted the round as a success (#53).
                        unmatched[field_id] = value
                        _LOGGER.debug(
                            "Control %s on device %s answered %s, which is not "
                            "one of its options",
                            field_id,
                            sn,
                            value,
                        )
                        continue
                    unmatched.pop(field_id, None)
                    self._ctrl_value_read_at[(sn, field_id)] = monotonic()
                    if setting_value(by_id[field_id], values.get(field_id)) is None:
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
                    if self._ctrl_value_retries[sn] >= self._control_value_budget(sn):
                        # Once per device per budget, and the only line that
                        # reports it now that the API layer keeps its own
                        # attempts at debug (#61). A control left unknown is
                        # worth a warning; the attempts themselves were not.
                        _LOGGER.warning(
                            "Giving up on %d control value(s) for device %s after "
                            "%d attempts, the last of which the API %s; ordinary "
                            "cloud telemetry still updates them, and reloading the "
                            "entry retries",
                            len(missing),
                            sn,
                            self._ctrl_value_retries[sn],
                            "did not answer" if unanswered else "answered with none",
                        )
            else:
                await self._refresh_known_control_values(
                    pn, devcode, devaddr, sn, controls, by_id, values
                )
            changed = values != before
        if changed:
            # Existing entities also need to see late read recovery. Preserve
            # the independent cloud refresh timer and revision counter.
            self.async_update_listeners()
        return controls, values

    async def _refresh_known_control_values(
        self,
        pn: str,
        devcode: int,
        devaddr: int,
        sn: str,
        controls: dict[str, Any],
        by_id: dict[str, Any],
        values: dict[str, str],
    ) -> None:
        """Re-read settings this integration already has a value for.

        Nothing else does. The retry rounds read only the fields with no
        value, and ordinary telemetry refreshes only those a collector repeats
        among its readings, so a setting changed anywhere other than Home
        Assistant stayed as it was first read for the life of the entry (#53).

        Only a revision that spent no round recovering unknown values gets
        here, so startup is unchanged: recovery keeps priority, and a device
        still missing values spends nothing on refreshing the ones it has.
        """
        if sn in self.stale_cloud_serials:
            # This device's payload is a retained one, so a live read of its
            # settings would almost certainly spend the round's deadline.
            return
        if self._ctrl_value_attempts.get(sn) == self.cloud_revision:
            return

        now = monotonic()
        covered = self._ctrl_cloud_refreshed.get(sn, set())
        candidates: list[tuple[float, str]] = []
        for config in controls.values():
            field_id = config.get("id")
            if not field_id or field_id in covered:
                continue
            if setting_value(config, values.get(field_id)) is None:
                # No value to refresh; this field belongs to the retry rounds.
                continue
            written_at = self._ctrl_write_at.get((sn, field_id))
            if (
                written_at is not None
                and now - written_at < CONTROL_VALUE_WRITE_GRACE_SECONDS
            ):
                continue
            read_at = self._ctrl_value_read_at.get((sn, field_id))
            # Never read explicitly: the value came from telemetry that has
            # since stopped carrying it, or from a write. Oldest there is.
            age = float("inf") if read_at is None else now - read_at
            interval = self._ctrl_refresh_interval.get(
                (sn, field_id), CONTROL_VALUE_REFRESH_BASE_INTERVAL_SECONDS
            )
            if age < interval:
                continue
            # How far past its own interval, so that a field the hardware
            # moves is followed closely without starving the rest: a stable
            # field overtakes it once it is twice as overdue.
            candidates.append((age / interval, field_id))

        if not candidates:
            return

        # Most overdue first, and by field id where that ties, so a round is
        # reproducible rather than dependent on dictionary order.
        candidates.sort(key=lambda item: (-item[0], item[1]))
        field_ids = [
            field_id for _, field_id in candidates[:CONTROL_VALUE_REFRESH_PER_ROUND]
        ]
        self._ctrl_value_attempts[sn] = self.cloud_revision
        fetched, _unanswered = await self._fetch_all_control_values(
            pn, devcode, devaddr, sn, field_ids
        )
        unmatched = self.ctrl_unmatched_values.setdefault(sn, {})
        for field_id, value in fetched.items():
            self._ctrl_value_read_at[(sn, field_id)] = monotonic()
            normalized = setting_value(by_id[field_id], value)
            if normalized is None:
                # Keep the value the entity is showing: an answer outside the
                # option list is not a reason to blank a setting that reads.
                unmatched[field_id] = value
                continue
            unmatched.pop(field_id, None)
            if normalized != values.get(field_id):
                _LOGGER.debug(
                    "Control %s on device %s changed to %s outside Home Assistant",
                    field_id,
                    sn,
                    normalized,
                )
                values[field_id] = normalized
                self._ctrl_refresh_interval[(sn, field_id)] = (
                    CONTROL_VALUE_REFRESH_FAST_INTERVAL_SECONDS
                )
            else:
                self._ctrl_refresh_interval[(sn, field_id)] = min(
                    self._ctrl_refresh_interval.get(
                        (sn, field_id), CONTROL_VALUE_REFRESH_BASE_INTERVAL_SECONDS
                    )
                    * 2,
                    CONTROL_VALUE_REFRESH_MAX_INTERVAL_SECONDS,
                )

    def record_control_write(self, sn: str, field_id: str, value: str) -> None:
        """Record a setting Home Assistant has just written.

        The entity shows the written value straight away, and the refresh
        rotation leaves the field alone until the inverter has had time to act
        on it. An accepted write is still not proof that it did.
        """
        if not sn or not field_id:
            return
        self.ctrl_value_cache.setdefault(sn, {})[field_id] = value
        self._ctrl_write_at[(sn, field_id)] = monotonic()

    def _control_value_budget(self, sn: str) -> int:
        """Return how many fruitless read rounds this device still gets.

        A round the API answered tells us the field has no value to give. A
        round it never answered tells us nothing, so those get the longer
        budget rather than retiring a control that reads intermittently.
        """
        if self._ctrl_value_unanswered.get(sn):
            return MAX_UNANSWERED_CONTROL_VALUE_RETRIES
        return MAX_CONTROL_VALUE_RETRIES

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
        covered = self._ctrl_cloud_refreshed.setdefault(sn, set())
        devcode = (self.data or {}).get(sn, {}).get("device", {}).get("devcode")
        for name, config in controls.items():
            field_id = config.get("id")
            # A profile may name the reading that carries this control's value,
            # where the collector answers the control's own name with a live
            # measurement instead.
            declared = control_value_reading(devcode, field_id)
            titles = (declared, name) if declared else (name,)
            value = setting_value(config, first_control_value(points, *titles))
            if field_id and value is not None:
                values[field_id] = value
                # This one refreshes itself on every cloud sample, so the
                # refresh rotation can spend its reads elsewhere.
                covered.add(field_id)

    async def _fetch_all_control_values(
        self,
        pn: str,
        devcode: int,
        devaddr: int,
        sn: str,
        field_ids: list[str],
    ) -> tuple[dict[str, str], bool]:
        """Read the given control values in parallel, within one deadline.

        Returns the values that were read, and whether any field went
        unanswered - a failed read or one still in flight at the deadline.
        That is what separates a field this hardware does not carry from a
        round that says nothing about it, and the retry budget keys off it.
        """
        if not field_ids:
            return {}, False

        sem = asyncio.Semaphore(5)

        async def _fetch_one(field_id: str) -> tuple[str, str | None, bool]:
            async with sem:
                try:
                    result = await self.api.get_device_control_value(
                        pn, devcode, devaddr, sn, field_id
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.debug(
                        "Failed to read control value %s for %s: %s",
                        field_id,
                        sn,
                        err,
                    )
                    return field_id, None, True
                return field_id, control_value(result.get("val")), False

        _LOGGER.info("Fetching %d control values for device %s", len(field_ids), sn)
        tasks = [asyncio.create_task(_fetch_one(fid)) for fid in field_ids]
        try:
            done, pending = await asyncio.wait(
                tasks, timeout=CONTROL_VALUE_ROUND_TIMEOUT_SECONDS
            )
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if pending:
            _LOGGER.info(
                "Abandoned %d of %d control value reads for device %s after %ds; "
                "a later refresh retries them",
                len(pending),
                len(field_ids),
                sn,
                CONTROL_VALUE_ROUND_TIMEOUT_SECONDS,
            )

        values: dict[str, str] = {}
        unanswered = bool(pending)
        for task in done:
            field_id, value, failed = task.result()
            if value is not None:
                values[field_id] = value
            unanswered = unanswered or failed

        _LOGGER.info(
            "Fetched %d/%d control values for device %s",
            len(values),
            len(field_ids),
            sn,
        )
        return values, unanswered

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
            self._async_update_support_issues(data)
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
        device_info.get("device", {}).get("devcode"), device_data, diagnostics
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


# What a support download may say about each configuration key. The file is
# attached to public issues, so this is an allowlist: a key that is not
# classified here is redacted rather than published, and
# ``test_every_config_key_is_classified`` fails until someone decides. The
# previous deny-list published anything nobody had thought about, which is how
# a reporter's collector and listen addresses reached a public issue (#53).
_PUBLISH = "publish"
_REDACT = "redact"
_HASH = "hash"
_DESCRIBE_ADDRESS = "describe_address"

_ENTRY_DISCLOSURE: dict[str, str] = {
    # Credentials and the session token: never, in any form.
    CONF_USERNAME: _REDACT,
    CONF_PASSWORD: _REDACT,
    CONF_COMPANY_KEY: _REDACT,
    "token": _REDACT,
    # Choices that shape behaviour and identify nothing.
    CONF_API_PROFILE: _PUBLISH,
    CONF_CONNECTION_TYPE: _PUBLISH,
    CONF_UPDATE_INTERVAL: _PUBLISH,
    CONF_LOCAL_MODE: _PUBLISH,
    CONF_LOCAL_POLL_INTERVAL: _PUBLISH,
    CONF_LOCAL_TCP_PORT: _PUBLISH,
    CONF_LOCAL_UDP_PORT: _PUBLISH,
    CONF_LOCAL_DEVICE_ADDRESS: _PUBLISH,
    CONF_LOCAL_DEVICE_CODE: _PUBLISH,
    CONF_LOCAL_REDIRECT_CONFIRMED: _PUBLISH,
    # The collector product number correlates two downloads of one account
    # without disclosing the number itself.
    CONF_LOCAL_EXPECTED_PN: _HASH,
    # Network addresses are described rather than printed; see below.
    CONF_LOCAL_LISTEN_IP: _DESCRIBE_ADDRESS,
    CONF_LOCAL_COLLECTOR_IP: _DESCRIBE_ADDRESS,
    CONF_LOCAL_COLLECTOR_IPS: _DESCRIBE_ADDRESS,
}
_REDACTED = "**redacted**"


def _network_label(value: Any, subnets: dict[str, int]) -> str:
    """Describe an address by family, scope and subnet, never by its value.

    Local mode fails in ways that depend on exactly these three facts: whether
    the collector is reachable at all (a public address is a misconfiguration),
    and whether Home Assistant listens on the same subnet the collector talks
    to. Replacing the addresses with a bare marker would take that away, so the
    numbering is per download and says only which addresses share a subnet.
    """
    text = str(value or "").strip()
    if not text:
        return text
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return _REDACTED
    prefix = 24 if address.version == 4 else 64
    network = str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))
    label = subnets.setdefault(network, len(subnets) + 1)
    scope = "private" if address.is_private else "public"
    return f"{scope} ipv{address.version} in subnet {label}"


# An address literal anywhere in free text. The IPv6 alternative also matches
# a clock ("10:32:34"), which is why every candidate is validated below before
# anything is replaced.
_ADDRESS_LITERAL = re.compile(
    r"(?<![\w.:])"
    r"(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})"
    r"(?![\w.])"
)


def _redacted_message(text: Any, subnets: dict[str, int]) -> str:
    """Return a free-text message with any address in it described, not printed.

    The allowlist below covers the configured values, and a local setup error
    carries the same addresses in prose: an exception from binding the listen
    socket reports "error while attempting to bind on address ('A.B.C.D',
    8899)", so a reporter's LAN address reached a public issue through the one
    field in the download that was passed through verbatim. The rest of the
    message is the diagnostic value and is kept, including the port.
    """

    def _describe(match: re.Match[str]) -> str:
        literal = match.group(0)
        try:
            ipaddress.ip_address(literal)
        except ValueError:
            return literal
        return _network_label(literal, subnets)

    return _ADDRESS_LITERAL.sub(_describe, str(text))


def _redacted_entry_values(
    values: Mapping[str, Any], subnets: dict[str, int] | None = None
) -> dict[str, Any]:
    """Return config values with credentials and identifiers removed.

    Only a key ``_ENTRY_DISCLOSURE`` classifies is published; anything else is
    redacted, so a configuration option added later cannot be disclosed by
    being forgotten.

    ``subnets`` carries the address grouping across both the data and the
    options of one download, so the same subnet gets the same number in both.
    """
    labels = subnets if subnets is not None else {}
    result: dict[str, Any] = {}
    for key, value in values.items():
        disclosure = _ENTRY_DISCLOSURE.get(key, _REDACT)
        if disclosure is _PUBLISH:
            result[key] = value
        elif disclosure is _HASH:
            result[key] = short_identity(value) if value else value
        elif disclosure is _DESCRIBE_ADDRESS:
            result[key] = (
                [_network_label(item, labels) for item in value]
                if isinstance(value, (list, tuple))
                else _network_label(value, labels)
            )
        else:
            # Redacted, and the key is kept so a reader can still tell a
            # configured value from an absent one.
            result[key] = _REDACTED if value not in (None, "") else value
    return result


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return one support report per device, with nothing identifying in it.

    Home Assistant offers this download on the integration card, and with no
    hook the request failed before reaching the integration: "Download
    diagnostics" on the hub did nothing useful. It now answers what every
    support thread opens with, for every device at once: which mode the entry
    runs in, which devcodes it sees, whether each is supported, partial or
    unsupported, and which readings reach no entity (#60).

    Serial numbers, aliases and collector product numbers are replaced by the
    ``sha256:`` correlation form, so two downloads of the same account can be
    compared without disclosing either.
    """
    subnets: dict[str, int] = {}
    report: dict[str, Any] = {
        "integration": {
            "version": VERSION,
            "connection_type": entry.data.get(
                CONF_CONNECTION_TYPE, CONNECTION_TYPE_CLOUD
            ),
            "local_mode": entry.options.get(CONF_LOCAL_MODE, LOCAL_MODE_DISABLED),
            "api_profile": resolve_api_profile(dict(entry.data)),
        },
        "entry_data": _redacted_entry_values(entry.data, subnets),
        "entry_options": _redacted_entry_values(entry.options, subnets),
    }

    coordinator: DessMonitorDataUpdateCoordinator | None = hass.data.get(
        DOMAIN, {}
    ).get(entry.entry_id)
    if coordinator is None:
        report["error"] = "The config entry is not loaded"
        return report

    report["coordinator"] = {
        "last_update_success": coordinator.last_update_success,
        "update_interval_seconds": (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        ),
        "cloud_revision": coordinator.cloud_revision,
        "devices_in_snapshot": len(coordinator.data or {}),
        "devices_on_a_retained_cloud_payload": len(coordinator.stale_cloud_serials),
        "hybrid": getattr(coordinator, "is_hybrid", False),
    }

    if getattr(coordinator, "is_hybrid", False):
        report["local"] = {
            "setup_errors": [
                _redacted_message(error, subnets)
                for error in getattr(coordinator, "local_setup_errors", ())
            ],
            "transports": [
                {
                    "connected": local.connected,
                    "last_update_success": local.last_update_success,
                    "device_code": local.device_code,
                    "devices": len(local.data or {}),
                    # What the local side actually saw. The hybrid overlay
                    # matches a local device to a cloud one by serial, or by
                    # collector and RS485 address together, and a device that
                    # matches nothing stays on cloud telemetry in silence. The
                    # file recorded only that a transport was connected, so a
                    # mismatch between an inverter answering locally at one
                    # address and the cloud listing it at another could not be
                    # seen in it at all (#61).
                    "devices_seen": [
                        _local_device_facts(serial, payload)
                        for serial, payload in sorted((local.data or {}).items())
                    ],
                }
                for local in getattr(coordinator, "locals", ())
            ],
        }

    report["devices"] = [
        await _build_device_support_report(coordinator, entry, serial, payload)
        for serial, payload in sorted((coordinator.data or {}).items())
    ]
    return report


def _local_device_facts(serial: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Describe one locally seen device, without naming it.

    Identities are the same correlation hashes the device reports carry, so a
    local device and a cloud one can be told apart and compared across a file
    without a serial number or a collector product number appearing in it.
    """
    device = payload.get("device") or {}
    collector = payload.get("collector") or {}
    return {
        "device_identity": short_identity(serial),
        "collector_identity": short_identity(collector.get("pn")),
        "device_address": device.get("devaddr"),
        "address_verified": device.get("local_address_verified"),
        "protocol": device.get("local_protocol"),
        "readings": len(payload.get("data") or []),
    }


def _control_read_state(
    coordinator: DessMonitorDataUpdateCoordinator,
    serial: str,
    control_fields: dict[str, Any],
) -> dict[str, Any]:
    """Say whether a control without a value is still being read for.

    A control that reads unknown looks identical whether the next refresh will
    ask again or the retry budget ran out rounds ago, and that is the first
    question behind a control that never recovers (#60, #61). The budget is
    three rounds that recover nothing when the API answered and had no value,
    and twelve when it never answered, because a read that times out says
    nothing about the field.
    """
    retries = _int_for(getattr(coordinator, "_ctrl_value_retries", None), serial)
    budget_for = getattr(coordinator, "_control_value_budget", None)
    budget = budget_for(serial) if callable(budget_for) else None
    if not isinstance(budget, int) or isinstance(budget, bool):
        budget = None
    unanswered = getattr(coordinator, "_ctrl_value_unanswered", None)
    unread = sum(
        1
        for field in control_fields.values()
        if isinstance(field, dict) and field.get("value") == _UNREAD
    )
    return {
        "fields": len(control_fields),
        "without_a_value": unread,
        "rounds_that_recovered_nothing": retries,
        "rounds_allowed": budget,
        "still_trying": budget is None or retries < budget,
        "last_round_went_unanswered": bool(
            unanswered.get(serial, False) if isinstance(unanswered, dict) else False
        ),
    }


def _int_for(mapping: Any, key: str) -> int:
    """Return a counter a coordinator keeps per device, or zero."""
    if not isinstance(mapping, dict):
        return 0
    value = mapping.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


async def _build_device_support_report(
    coordinator: DessMonitorDataUpdateCoordinator,
    entry: ConfigEntry,
    serial: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build one device's report, tolerating a device the cloud cannot answer for.

    A failed control read must not fail the whole download: a reporter whose
    account is timing out is exactly the one who needs to attach this file.
    """
    device_meta = payload.get("device", {})
    collector_meta = payload.get("collector", {})
    readings = payload.get("data", [])

    control_fields: dict[str, Any] = {}
    parameters: dict[str, Any] = {}
    control_error: str | None = None
    try:
        control_fields, parameters, control_error = await _fetch_control_details(
            coordinator, serial, payload, readings
        )
    except Exception as err:  # pylint: disable=broad-except
        control_error = str(err)
        _LOGGER.debug("Control details unavailable for device %s: %s", serial, err)

    report = build_support_report(
        devcode=device_meta.get("devcode"),
        readings=readings,
        device_serial=serial,
        collector_product_number=collector_meta.get("pn"),
        device_address=device_meta.get("devaddr"),
        control_fields=control_fields,
        parameters=parameters,
        api_profile=resolve_api_profile(dict(entry.data)),
        integration_version=VERSION,
    )
    report["control_reads"] = _control_read_state(coordinator, serial, control_fields)
    report["data_source"] = _extract_sensor_value(readings, "Data Source")
    report["last_update"] = _extract_sensor_value(readings, "Timestamp", "Unknown")
    if control_error:
        report["control_error"] = control_error
    report["checksum"] = report_checksum(report)
    return report


def _build_base_diagnostics(
    device_sn: str, device_info: dict[str, Any], datapoint_count: int
) -> dict[str, Any]:
    """Return the base diagnostics structure for a device."""
    device_meta = device_info.get("device", {})
    collector_meta = device_info.get("collector", {})

    # Home Assistant offers "Download diagnostics" on each device as well as on
    # the integration entry, and a reporter attaches whichever one they found.
    # This file used to print the serial number, the collector product number
    # and the user's own alias, while the hub file replaced all three with the
    # correlation hash and the support guide promised the download carried no
    # identifiers. Both files now keep that promise, and two downloads of one
    # device still carry the same hash so they can be compared (#53).
    return {
        "device_info": {
            "serial_number": short_identity(device_sn),
            "alias": short_identity(device_meta.get("alias")),
            "firmware_version": collector_meta.get("fireware", "Unknown"),
            "collector_pn": short_identity(collector_meta.get("pn")),
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
# A control this integration has no value for. It is not the same as a value
# of zero or an empty setting, and a support file has to say which it means.
_UNREAD = "Not read"
# Nor is it the same as a control the API answered for with a value the
# control's own options do not offer, which no entity can display.
_UNMATCHED = "not one of the options offered"

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

    formatted_fields = _format_control_fields(
        control_fields,
        device_data,
        _known_control_values(coordinator, device_sn),
        device_meta.get("devcode"),
    )
    _LOGGER.debug(
        "Added %d control fields and %d parameters to diagnostics for device %s",
        len(formatted_fields),
        len(device_parameters),
        device_sn,
    )
    return formatted_fields, device_parameters, None


def _known_control_values(
    coordinator: DessMonitorDataUpdateCoordinator, device_sn: str
) -> Mapping[str, str]:
    """Return what this device's controls have been read as, by field id.

    Most control fields never appear in ordinary telemetry, so a diagnostics
    file built from the telemetry payload alone claimed no value for controls
    Home Assistant was displaying one for. The coordinator's cache is where an
    explicit read lands, and it is the same value the entities show.

    A control the API answered with a value outside its own option list is
    neither of those. The entities cannot show it, so it is reported as what
    was read rather than as "Not read": the reporter in #53 had a control the
    cloud answered on every round while the file said it had never been read,
    which is the opposite diagnosis (#61 asked the file to tell those apart).
    """
    cache = getattr(coordinator, "ctrl_value_cache", None)
    values = cache.get(device_sn) if isinstance(cache, dict) else None
    reported = dict(values) if isinstance(values, dict) else {}
    unmatched = getattr(coordinator, "ctrl_unmatched_values", None)
    answers = unmatched.get(device_sn) if isinstance(unmatched, dict) else None
    if isinstance(answers, dict):
        for field_id, answer in answers.items():
            reported.setdefault(field_id, f"{answer} ({_UNMATCHED})")
    return reported


def _read_control_value(
    field_data: Mapping[str, Any], known_values: Mapping[str, str] | None
) -> str | None:
    """Return the value read for this control field, if one has been."""
    field_id = field_data.get("id")
    if not known_values or not isinstance(field_id, str):
        return None
    return known_values.get(field_id)


def _format_control_fields(
    control_fields: dict[str, Any],
    device_data: list[dict[str, Any]],
    known_values: Mapping[str, str] | None = None,
    devcode: Any = None,
) -> dict[str, Any]:
    """Format control field metadata for diagnostics output."""
    formatted: dict[str, Any] = {}
    known_values = known_values or {}

    for field_name, field_data in control_fields.items():
        if field_data.get("type") == "options":
            formatted[field_name] = _format_option_field(
                field_name, field_data, device_data, known_values, devcode
            )
        else:
            formatted[field_name] = _format_numeric_field(
                field_name, field_data, device_data, known_values
            )

    return formatted


def _format_option_field(
    field_name: str,
    field_data: dict[str, Any],
    device_data: list[dict[str, Any]],
    known_values: Mapping[str, str] | None = None,
    devcode: Any = None,
) -> dict[str, Any]:
    """Format control fields that expose selectable options."""
    declared = control_value_reading(devcode, field_data.get("id"))
    sensor_value = _extract_sensor_value(device_data, field_name)
    if declared:
        sensor_value = _extract_sensor_value(device_data, declared, sensor_value)
    current_value = _resolve_option_value(
        field_name, field_data, sensor_value, device_data, known_values or {}
    )

    options_display = [
        f"{key}: {label}" for key, label in field_data.get("options", {}).items()
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
    known_values: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Format numeric control fields, reporting only what was read."""
    current_value = _extract_sensor_value(device_data, field_name)
    if current_value is None:
        read_value = _read_control_value(field_data, known_values)
        current_value = _UNREAD if read_value is None else read_value

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
    known_values: Mapping[str, str] | None = None,
):
    """Resolve option value with priority mappings when available."""
    if sensor_value and field_name in PRIORITY_MAPPINGS:
        desired_key = _match_priority_option(field_name, str(sensor_value))
        if desired_key is not None:
            return _lookup_option_value(field_data, desired_key)

    # Only a value that corresponds to one of the control's options is
    # reported. A collector answers a control's name with a live measurement on
    # some devcodes - devcode 2376 reports 229.8 V for an Output Voltage whose
    # options are 220, 230 and 240 - and the file used to present that as the
    # control's value while the entity, which checks, showed none.
    telemetry = control_value(sensor_value)
    if telemetry is not None:
        option_key = option_key_for(field_data.get("options", {}), telemetry)
        if option_key is not None:
            return _lookup_option_value(field_data, option_key)

    # Most controls never appear in telemetry. Their value comes from an
    # explicit read, which the coordinator caches by field id.
    read_value = _read_control_value(field_data, known_values)
    if read_value is not None:
        return _lookup_option_value(field_data, read_value)

    return _UNREAD


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
    options = field_data.get("options", {})
    if option_key in options:
        return options[option_key]
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
    devcode: Any,
    device_data: list[dict[str, Any]],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Create diagnostics summary block.

    ``total_sensors_created`` counted the readings listed in
    ``coordinator.data["sensor_types"]``, a key nothing has ever set, so it
    reported 0 on every healthy device. It now counts the distinct canonical
    sensors this device's readings resolve to, which is what the sensor
    platform creates, and ``readings_without_a_sensor`` names the rest. That
    pair is the first thing worth knowing when a reporter says a reading is
    missing.

    Coverage is decided by ``support_report.resolved_key_for``, the single
    predicate the sensor platform, this summary, the hub report and the
    maintainer tooling all ask.
    """
    resolved: set[str] = set()
    unresolved: list[str] = []
    for data_point in device_data:
        title = data_point.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        key = resolved_key_for(devcode, data_point)
        if key:
            resolved.add(key)
        elif not is_attribute_reading(title):
            unresolved.append(title.strip())

    return {
        "total_sensors_created": len(resolved),
        "readings_without_a_sensor": sorted(set(unresolved)),
        "last_update": _extract_sensor_value(device_data, "Timestamp", "Unknown"),
        "control_fields_found": len(diagnostics.get("configuration", {})),
        "parameters_found": len(diagnostics.get("parameters", {})),
    }
