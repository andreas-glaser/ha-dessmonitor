"""The DessMonitor integration."""

from __future__ import annotations

import logging
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
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN, UNITS
from .device_support import is_devcode_supported, map_sensor_title

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

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

    api = _create_api_client(hass, entry)
    await _authenticate_api_client(api)

    coordinator = await _create_coordinator(hass, entry, api)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("DessMonitor integration setup completed successfully")
    return True


def _create_api_client(hass: HomeAssistant, entry: ConfigEntry) -> DessMonitorAPI:
    """Create API client with storage-backed token handling."""
    username = entry.data["username"]
    company_key = entry.data.get("company_key", "bnrl_frRFjEz8Mkn")
    _LOGGER.debug("Initializing API client for user: %s", username)

    store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_auth")

    return DessMonitorAPI(
        username=username,
        password=entry.data["password"],
        company_key=company_key,
        store=store,
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

    coordinator = DessMonitorDataUpdateCoordinator(hass, api, update_interval)
    _LOGGER.debug("Created data update coordinator, performing first refresh")

    try:
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("First data refresh completed successfully")
    except DessMonitorError as err:
        _LOGGER.warning(
            "DessMonitor data refresh failed during setup (will retry): %s", err
        )
        raise ConfigEntryNotReady from err
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.error("Failed to perform initial data refresh: %s", err)
        _LOGGER.debug("Initial refresh error details", exc_info=True)
        raise ConfigEntryNotReady from err

    return coordinator


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading DessMonitor integration entry: %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Coordinator removed and platforms unloaded successfully")

        if hasattr(coordinator, "api") and hasattr(coordinator.api, "close"):
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
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


class DessMonitorDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the DessMonitor API."""

    def __init__(
        self, hass: HomeAssistant, api: DessMonitorAPI, update_interval: int
    ) -> None:
        """Initialize."""
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Starting data update cycle")
        try:
            collectors = await self._fetch_collectors()
            data = await self._gather_all_device_data(collectors)
            await self._merge_summary_data(data, bool(collectors))

            _LOGGER.info(
                "Data update completed successfully: %d devices total", len(data)
            )
            return data
        except UpdateFailed:
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "Error communicating with DessMonitor API during update: %s", err
            )
            _LOGGER.debug("Data update error details", exc_info=True)
            raise UpdateFailed(
                f"Error communicating with DessMonitor API: {err}"
            ) from err

    async def _fetch_collectors(self) -> list[dict[str, Any]]:
        """Fetch list of collectors from the API."""
        _LOGGER.debug("Fetching collectors list")
        collectors, _projects = await self.api.get_collectors()
        _LOGGER.debug("Found %d collectors to process", len(collectors))
        return collectors

    async def _gather_all_device_data(
        self, collectors: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Collect last known data for all devices."""
        data: dict[str, Any] = {}
        errors: list[str] = []

        for index, collector in enumerate(collectors, start=1):
            collector_id = collector["pn"]
            _LOGGER.debug(
                "Processing collector %d/%d: %s",
                index,
                len(collectors),
                collector_id,
            )

            try:
                collector_devices = await self._fetch_devices_for_collector(collector)
            except DessMonitorError as err:
                _LOGGER.warning("Skipping collector %s: %s", collector_id, err)
                errors.append(f"{collector_id}: {err}")
                continue

            data.update(collector_devices)

        if not data and errors:
            raise UpdateFailed(f"All collectors failed: {'; '.join(errors)}")

        return data

    async def _fetch_devices_for_collector(
        self, collector: dict[str, Any]
    ) -> dict[str, Any]:
        """Fetch data for all devices under a collector."""
        collector_id = collector["pn"]
        devices_response = await self.api.get_collector_devices(collector_id)
        device_list = devices_response.get("dev", [])
        _LOGGER.debug("Collector %s has %d devices", collector_id, len(device_list))

        device_data: dict[str, Any] = {}
        for index, device in enumerate(device_list, start=1):
            device_sn = device["sn"]
            _LOGGER.debug(
                "Processing device %d/%d: %s (devcode=%s, devaddr=%s)",
                index,
                len(device_list),
                device_sn,
                device["devcode"],
                device["devaddr"],
            )

            try:
                last_data = await self._fetch_device_last_data(collector_id, device)
            except DessMonitorError as err:
                _LOGGER.warning(
                    "Skipping device %s (collector %s): %s",
                    device_sn,
                    collector_id,
                    err,
                )
                continue

            device_data[device_sn] = {
                "collector": collector,
                "device": device,
                "data": last_data,
            }

        return device_data

    async def _fetch_device_last_data(
        self, collector_id: str, device: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Fetch latest datapoints for a single device."""
        device_sn = device["sn"]
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

            unique_summary_points = [
                point
                for point in summary_points
                if point.get("title")
                and point.get("title") not in existing_titles
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
VOLTAGE_FALLBACKS = {
    "High DC": "58.4 V (Est.)",
    "Low DC": "44.0 V (Est.)",
    "Bulk": "57.6 V (Est.)",
    "Floating": "56.4 V (Est.)",
}
VOLTAGE_FIELD_NAMES = {
    "High DC Protection Voltage",
    "Bulk Charging Voltage",
    "Floating Charging Voltage",
    "Low DC Protection Voltage In Mains Mode",
    "Low DC Protection Voltage In Off-Grid Mode",
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
    """Format numeric control fields with sensible fallbacks."""
    current_value = _extract_sensor_value(device_data, field_name, default="Not Set")

    if field_name in VOLTAGE_FIELD_NAMES and current_value == "Not Set":
        current_value = _estimate_voltage_value(field_name)

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


def _estimate_voltage_value(field_name: str) -> str:
    """Return voltage fallback based on field name heuristics."""
    for key, value in VOLTAGE_FALLBACKS.items():
        if key in field_name:
            return value
    return "Not Set"


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
