"""DessMonitor diagnostic sensors platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import (
    BATTERY_TYPES,
    CHARGER_PRIORITIES,
    CURRENT_UNIT,
    DOMAIN,
    OUTPUT_PRIORITIES,
    VOLTAGE_UNIT,
)

_LOGGER = logging.getLogger(__name__)

DIAGNOSTIC_SENSORS = {
    "Output Priority": {
        "name": "Output Priority",
        "unit": "",
        "device_class": "enum",
        "options": OUTPUT_PRIORITIES,
        "icon": "mdi:electric-switch",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bse_eybond_ctrl_49",
    },
    "Charger Source Priority": {
        "name": "Charger Source Priority",
        "unit": "",
        "device_class": "enum",
        "options": CHARGER_PRIORITIES,
        "icon": "mdi:battery-charging",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_75",
    },
    "Battery Type": {
        "name": "Battery Type",
        "unit": "",
        "device_class": "enum",
        "options": BATTERY_TYPES,
        "icon": "mdi:battery",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_66",
    },
    "Max Charging Current": {
        "name": "Max Charging Current",
        "unit": CURRENT_UNIT,
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-dc",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_76",
    },
    "Max AC Charging Current": {
        "name": "Max AC Charging Current",
        "unit": CURRENT_UNIT,
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_77",
    },
    "High DC Protection Voltage": {
        "name": "High DC Protection Voltage",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:flash-triangle",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_67",
    },
    "Low DC Protection Voltage (Mains)": {
        "name": "Low DC Protection Voltage (Mains)",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:flash-triangle-outline",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_71",
    },
    "Low DC Protection Voltage (Off-Grid)": {
        "name": "Low DC Protection Voltage (Off-Grid)",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:flash-triangle-outline",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_73",
    },
    "Bulk Charging Voltage": {
        "name": "Bulk Charging Voltage",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:battery-charging-high",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_68",
    },
    "Floating Charging Voltage": {
        "name": "Floating Charging Voltage",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:battery-charging-medium",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bat_eybond_ctrl_69",
    },
    "Battery EQ Mode": {
        "name": "Battery EQ Mode",
        "unit": "",
        "device_class": "enum",
        "options": ["Disable", "Enable"],
        "icon": "mdi:battery-sync",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "sys_eybond_ctrl_60",
    },
    "Input Voltage Range": {
        "name": "Input Voltage Range",
        "unit": "",
        "device_class": "enum",
        "options": ["Appliances", "UPS", "Generator"],
        "icon": "mdi:sine-wave",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "bse_eybond_ctrl_50",
    },
    "Power Saving Mode": {
        "name": "Power Saving Mode",
        "unit": "",
        "device_class": "enum",
        "options": ["Disable", "Enable"],
        "icon": "mdi:power-sleep",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "sys_eybond_ctrl_55",
    },
    "Auto Restart Overload": {
        "name": "Auto Restart Overload",
        "unit": "",
        "device_class": "enum",
        "options": ["Disable", "Enable"],
        "icon": "mdi:restart",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "sys_eybond_ctrl_56",
    },
    "Overload Bypass": {
        "name": "Overload Bypass",
        "unit": "",
        "device_class": "enum",
        "options": ["Disable", "Enable"],
        "icon": "mdi:bypass",
        "entity_category": "diagnostic",
        "enabled_default": False,
        "control_field_id": "sys_eybond_ctrl_58",
    },
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up DessMonitor diagnostic sensor entities."""
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for device_sn, device_info in coordinator.data.items():
        device_meta = device_info.get("device", {})
        collector_meta = device_info.get("collector", {})

        for sensor_key, sensor_config in DIAGNOSTIC_SENSORS.items():
            entities.append(
                DessMonitorDiagnosticSensor(
                    coordinator=coordinator,
                    device_sn=device_sn,
                    device_meta=device_meta,
                    collector_meta=collector_meta,
                    sensor_key=sensor_key,
                    sensor_config=sensor_config,
                )
            )

    async_add_entities(entities)
    _LOGGER.debug(
        "Added %d diagnostic sensors for %d devices",
        len(entities),
        len(coordinator.data),
    )


class DessMonitorDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Representation of a DessMonitor diagnostic sensor."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
        sensor_key: str,
        sensor_config: dict[str, Any],
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator)

        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._sensor_key = sensor_key
        self._sensor_config = sensor_config
        self._control_field_id = sensor_config.get("control_field_id")

        device_alias = device_meta.get("alias", "Unknown Device")

        self._attr_unique_id = (
            f"{device_sn}_{sensor_key.lower().replace(' ', '_')}_diagnostic"
        )
        self._attr_name = f"{device_alias} {sensor_config['name']}"

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = sensor_config.get(
            "enabled_default", False
        )
        self._attr_icon = sensor_config.get("icon")

        if sensor_config.get("device_class") == "enum":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = sensor_config.get("options", [])
        elif sensor_config.get("device_class") == "voltage":
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_native_unit_of_measurement = sensor_config.get("unit")
        elif sensor_config.get("device_class") == "current":
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_native_unit_of_measurement = sensor_config.get("unit")

        if sensor_config.get("state_class") == "measurement":
            self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_sn)},
            "name": device_alias,
            "manufacturer": "DessMonitor",
            "model": f"Collector {collector_meta.get('pn', 'Unknown')}",
            "sw_version": collector_meta.get("fireware", "Unknown"),
        }

    @property
    def native_value(self) -> str | float | None:
        """Return the current value of the diagnostic sensor."""
        control_fields_data = getattr(
            self.coordinator, "_control_fields_cache", {}
        ).get(self._device_sn)

        if control_fields_data and self._control_field_id in control_fields_data:
            field_data = control_fields_data[self._control_field_id]

            if self._sensor_config.get("device_class") == "enum":
                current_key = field_data.get("current_value")
                if current_key is not None:
                    option_mapping = self._get_option_mapping()
                    return option_mapping.get(str(current_key), f"Option {current_key}")
                return "Unknown"
            else:
                return field_data.get("current_value")

        device_data = self.coordinator.data.get(self._device_sn, {}).get("data", [])
        for data_point in device_data:
            if data_point.get("title") == self._sensor_key:
                value = data_point.get("val")
                if self._sensor_config.get("device_class") in ["voltage", "current"]:
                    try:
                        return float(value) if value is not None else None
                    except (ValueError, TypeError):
                        return None
                return value

        return None

    def _get_option_mapping(self) -> dict[str, str]:
        """Get mapping from control field option keys to display text."""
        if self._sensor_key == "Output Priority":
            return {"0": "UTI", "1": "SOL", "2": "SBU", "3": "SUB"}
        elif self._sensor_key == "Charger Source Priority":
            return {
                "0": "Utility First",
                "1": "PV First",
                "2": "PV Is At The Same Level As Utility",
                "3": "Only PV",
            }
        elif self._sensor_key == "Battery Type":
            return {
                "0": "AGM",
                "1": "FLD",
                "2": "USER",
                "3": "Li1",
                "4": "Li2",
                "5": "Li3",
                "6": "Li4",
            }
        elif self._sensor_key in [
            "Battery EQ Mode",
            "Power Saving Mode",
            "Auto Restart Overload",
            "Overload Bypass",
        ]:
            return {"0": "Disable", "1": "Enable"}
        elif self._sensor_key == "Input Voltage Range":
            return {"0": "Appliances", "1": "UPS", "2": "Generator"}

        return {}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self._device_sn in self.coordinator.data
        )
