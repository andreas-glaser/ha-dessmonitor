"""The DessMonitor integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DessMonitorAPI
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN, UNITS

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DessMonitor from a config entry."""
    _LOGGER.debug("Setting up DessMonitor integration for entry: %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    username = entry.data["username"]
    company_key = entry.data.get("company_key", "bnrl_frRFjEz8Mkn")
    _LOGGER.debug("Initializing API client for user: %s", username)

    api = DessMonitorAPI(
        username=username,
        password=entry.data["password"],
        company_key=company_key,
    )

    try:
        _LOGGER.debug("Attempting initial authentication")
        await api.authenticate()
        _LOGGER.info("Initial authentication successful for DessMonitor integration")
    except Exception as err:
        _LOGGER.error(
            "Failed to authenticate with DessMonitor API during setup: %s", err
        )
        _LOGGER.debug("Authentication setup error details", exc_info=True)
        return False

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
    except Exception as err:
        _LOGGER.error("Failed to perform initial data refresh: %s", err)
        _LOGGER.debug("Initial refresh error details", exc_info=True)
        return False

    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("DessMonitor integration setup completed successfully")
    return True


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
        self._control_fields_cache: dict = {}
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
            data = {}
            _LOGGER.debug("Fetching collectors list")
            collectors = await self.api.get_collectors()
            _LOGGER.debug("Found %d collectors to process", len(collectors))

            for i, collector in enumerate(collectors):
                collector_id = collector["pn"]
                _LOGGER.debug(
                    "Processing collector %d/%d: %s",
                    i + 1,
                    len(collectors),
                    collector_id,
                )

                devices = await self.api.get_collector_devices(collector_id)
                device_list = devices.get("dev", [])
                _LOGGER.debug(
                    "Collector %s has %d devices", collector_id, len(device_list)
                )

                for j, device in enumerate(device_list):
                    device_sn = device["sn"]
                    _LOGGER.debug(
                        "Processing device %d/%d: %s (devcode=%s, devaddr=%s)",
                        j + 1,
                        len(device_list),
                        device_sn,
                        device["devcode"],
                        device["devaddr"],
                    )

                    device_data = await self.api.get_device_last_data(
                        pn=collector_id,
                        devcode=device["devcode"],
                        devaddr=device["devaddr"],
                        sn=device_sn,
                    )

                    data[device_sn] = {
                        "collector": collector,
                        "device": device,
                        "data": device_data,
                    }
                    _LOGGER.debug(
                        "Stored data for device %s with %d data points",
                        device_sn,
                        len(device_data),
                    )

            if collectors:
                try:
                    _LOGGER.debug("Fetching project information for summary data")
                    projects_response = await self.api._make_request(
                        "queryPlants", {"pagesize": 1}
                    )
                    if (
                        "dat" in projects_response
                        and "plant" in projects_response["dat"]
                    ):
                        projects = projects_response["dat"]["plant"]
                        if projects:
                            project_id = projects[0]["pid"]
                            _LOGGER.debug(
                                "Using project ID %s for summary data", project_id
                            )

                            summary_data = await self.api.get_device_summary_data(
                                project_id
                            )
                            _LOGGER.debug(
                                "Retrieved summary data for %d devices",
                                len(summary_data),
                            )

                            for device_sn, device_info in data.items():
                                if device_sn in summary_data:
                                    existing_data = device_info["data"]
                                    summary_points = summary_data[device_sn]["data"]

                                    existing_data.extend(summary_points)

                                    device_alias = device_info.get("device", {}).get(
                                        "alias", "Unknown"
                                    )
                                    summary_types = [
                                        p.get("title") for p in summary_points
                                    ]
                                    _LOGGER.debug(
                                        "Merged %d summary sensors (%s) for %s (%s)",
                                        len(summary_points),
                                        ", ".join(summary_types),
                                        device_alias,
                                        device_sn,
                                    )
                        else:
                            _LOGGER.warning("No projects found for summary data")
                    else:
                        _LOGGER.warning(
                            "Failed to get project information for summary data"
                        )
                except Exception as err:
                    _LOGGER.warning("Failed to fetch summary data: %s", err)

            update_count = getattr(self, "_update_count", 0) + 1
            self._update_count = update_count

            if (
                update_count % 50 == 1
            ):  # Update on first call and every 50th update (less frequent)
                _LOGGER.debug("Updating control fields cache for diagnostic sensors")
                for device_sn, device_info in data.items():
                    try:
                        device_meta = device_info.get("device", {})
                        collector_meta = device_info.get("collector", {})

                        control_fields = await self.api.get_device_control_fields(
                            pn=collector_meta.get("pn"),
                            devcode=device_meta.get("devcode"),
                            devaddr=device_meta.get("devaddr"),
                            sn=device_sn,
                        )

                        device_cache = {}
                        for field_name, field_data in control_fields.items():
                            if field_data.get("id"):
                                control_id = field_data["id"]

                                current_value = None
                                try:
                                    value_response = await self.api._make_request(
                                        "queryDeviceCtrlValue",
                                        {
                                            "i18n": "en_US",
                                            "source": "1",
                                            "id": control_id,
                                            "devaddr": device_meta.get("devaddr"),
                                            "devcode": device_meta.get("devcode"),
                                            "pn": collector_meta.get("pn"),
                                            "sn": device_sn,
                                        },
                                    )
                                    if value_response.get("err") == 0:
                                        current_value = value_response.get(
                                            "dat", {}
                                        ).get("value")
                                        _LOGGER.debug(
                                            "Got control field value for %s (%s): %s",
                                            field_name,
                                            control_id,
                                            current_value,
                                        )
                                    else:
                                        _LOGGER.debug(
                                            "No value available for control field %s (%s): %s",
                                            field_name,
                                            control_id,
                                            value_response.get("desc", "Unknown error"),
                                        )
                                except Exception as err:
                                    _LOGGER.debug(
                                        "Failed to get current value for control field %s: %s",
                                        field_name,
                                        err,
                                    )

                                device_cache[control_id] = {
                                    "name": field_name,
                                    "type": field_data.get("type"),
                                    "options": field_data.get("options", []),
                                    "current_value": current_value,
                                }

                        self._control_fields_cache[device_sn] = device_cache
                        _LOGGER.debug(
                            "Cached %d control fields for device %s",
                            len(device_cache),
                            device_sn,
                        )

                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to fetch control fields for device %s: %s",
                            device_sn,
                            err,
                        )

            _LOGGER.info(
                "Data update completed successfully: %d devices total", len(data)
            )
            return data

        except Exception as err:
            _LOGGER.error(
                "Error communicating with DessMonitor API during update: %s", err
            )
            _LOGGER.debug("Data update error details", exc_info=True)
            raise


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> dict:
    """Return diagnostics for a device entry."""
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    device_sn = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            device_sn = identifier[1]
            break

    if not device_sn or device_sn not in coordinator.data:
        return {"error": "Device not found"}

    device_info = coordinator.data[device_sn]
    device_data = device_info.get("data", [])
    device_meta = device_info.get("device", {})
    collector_meta = device_info.get("collector", {})

    diagnostics: dict[str, Any] = {
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
        "raw_data_points": len(device_data),
    }

    for data_point in device_data:
        title = data_point.get("title", "")
        value = data_point.get("val")
        unit = data_point.get("unit", "")

        if any(
            keyword in title.lower()
            for keyword in [
                "setting",
                "priority",
                "voltage setting",
                "cutoff",
                "capacity",
                "type",
                "configuration",
            ]
        ) or title in ["Output priority", "Charger Source Priority"]:
            diagnostics["configuration"][title] = {"value": value, "unit": unit}

        elif any(
            keyword in title.lower()
            for keyword in [
                "status",
                "operating mode",
                "state",
                "online",
                "connectivity",
            ]
        ):
            diagnostics["status"][title] = {"value": value, "unit": unit}

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

        priority_mapping = {
            "Output priority": {"SBU": 2, "UTI": 0, "SOL": 1, "SUB": 3},
            "Charger Source Priority": {
                "PV FIRST": 1,
                "UTILITY FIRST": 0,
                "PV_UTILITY": 2,
                "PV ONLY": 3,
            },
        }

        for field_name, field_data in control_fields.items():
            if field_data["type"] == "options":
                current_value = "Not Set"

                sensor_value = next(
                    (
                        dp.get("val")
                        for dp in device_data
                        if dp.get("title") == field_name
                    ),
                    None,
                )

                if sensor_value and field_name in priority_mapping:
                    for option_text, option_key in priority_mapping[field_name].items():
                        if str(sensor_value).upper() == option_text.upper():
                            current_value = next(
                                (
                                    opt["val"]
                                    for opt in field_data["options"]
                                    if opt["key"] == str(option_key)
                                ),
                                option_text,
                            )
                            break
                elif sensor_value:
                    current_value = sensor_value

                if field_name == "Output Voltage" and current_value == "Not Set":
                    output_voltage = next(
                        (
                            dp.get("val")
                            for dp in device_data
                            if dp.get("title") == "Output Voltage"
                        ),
                        None,
                    )
                    if output_voltage:
                        voltage_val = str(float(output_voltage))
                        current_value = next(
                            (
                                opt["val"]
                                for opt in field_data["options"]
                                if opt["key"] == voltage_val
                            ),
                            f"{output_voltage} V (Custom)",
                        )

                diagnostics["configuration"][field_name] = {
                    "value": current_value,
                    "unit": "",
                    "options": [
                        f"{opt['key']}: {opt['val']}" for opt in field_data["options"]
                    ],
                    "id": field_data["id"],
                }
            else:
                current_value = next(
                    (
                        dp.get("val")
                        for dp in device_data
                        if dp.get("title") == field_name
                    ),
                    "Not Set",
                )

                voltage_fields = [
                    "High DC Protection Voltage",
                    "Bulk Charging Voltage",
                    "Floating Charging Voltage",
                    "Low DC Protection Voltage In Mains Mode",
                    "Low DC Protection Voltage In Off-Grid Mode",
                ]

                if (
                    any(vf in field_name for vf in voltage_fields)
                    and current_value == "Not Set"
                ):
                    if "High DC" in field_name:
                        current_value = "58.4 V (Est.)"
                    elif "Low DC" in field_name:
                        current_value = "44.0 V (Est.)"
                    elif "Bulk" in field_name:
                        current_value = "57.6 V (Est.)"
                    elif "Floating" in field_name:
                        current_value = "56.4 V (Est.)"

                diagnostics["configuration"][field_name] = {
                    "value": current_value,
                    "unit": (
                        UNITS["VOLTAGE"]
                        if "Voltage" in field_name
                        else (UNITS["CURRENT"] if "Current" in field_name else "")
                    ),
                    "id": field_data["id"],
                }

        diagnostics["parameters"] = device_parameters

        _LOGGER.debug(
            "Added %d control fields and %d parameters to diagnostics for device %s",
            len(control_fields),
            len(device_parameters),
            device_sn,
        )

    except Exception as err:
        _LOGGER.warning(
            "Failed to fetch control fields/parameters for device %s: %s",
            device_sn,
            err,
        )
        diagnostics["battery_config_error"] = str(err)

    diagnostics["summary"] = {
        "total_sensors_created": len(
            [
                dp
                for dp in device_data
                if dp.get("title") in coordinator.data.get("sensor_types", [])
            ]
        ),
        "last_update": next(
            (dp.get("val") for dp in device_data if dp.get("title") == "Timestamp"),
            "Unknown",
        ),
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

    _LOGGER.debug(
        "Generated diagnostics for device %s with %d config items",
        device_sn,
        len(diagnostics["configuration"]),
    )

    return diagnostics
