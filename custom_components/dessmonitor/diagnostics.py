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
from .const import CHARGER_PRIORITIES, DOMAIN, OUTPUT_PRIORITIES
from .device_support import map_charger_priority, map_output_priority
from .utils import create_device_info

_LOGGER = logging.getLogger(__name__)

# Diagnostic sensors that get their data from the regular API (queryDeviceLastData)
# These sensors show device configuration/status that's already included in the regular data feed
DIAGNOSTIC_SENSORS = {
    "Output priority": {
        "name": "Output Priority",
        "unit": "",
        "device_class": "enum",
        "options": OUTPUT_PRIORITIES,
        "icon": "mdi:electric-switch",
        "entity_category": "diagnostic",
        "enabled_default": False,
    },
    "Charger Source Priority": {
        "name": "Charger Source Priority",
        "unit": "",
        "device_class": "enum",
        "options": CHARGER_PRIORITIES,
        "icon": "mdi:battery-charging",
        "entity_category": "diagnostic",
        "enabled_default": False,
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
        existing_titles = {
            str(data_point.get("title")).strip().lower()
            for data_point in device_info.get("data", [])
            if data_point.get("title")
        }

        for sensor_key, sensor_config in DIAGNOSTIC_SENSORS.items():
            if sensor_key.lower() in existing_titles:
                _LOGGER.debug(
                    "Skipping diagnostic sensor %s for device %s because primary sensor "
                    "exists",
                    sensor_key,
                    device_sn,
                )
                continue

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
            self._attr_options = self._build_enum_options(sensor_config)
        elif sensor_config.get("device_class") == "voltage":
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_native_unit_of_measurement = sensor_config.get("unit")
        elif sensor_config.get("device_class") == "current":
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_native_unit_of_measurement = sensor_config.get("unit")

        if sensor_config.get("state_class") == "measurement":
            self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )

    @property
    def native_value(self) -> str | float | None:
        """Return the current value of the diagnostic sensor."""
        # Get the already-transformed data from the coordinator
        device_data = self.coordinator.data.get(self._device_sn, {}).get("data", [])
        device_meta = self.coordinator.data.get(self._device_sn, {}).get("device", {})
        devcode = device_meta.get("devcode")

        for data_point in device_data:
            if data_point.get("title") == self._sensor_key:
                # Apply devcode transformations if available
                if devcode:
                    from .device_support import apply_devcode_transformations

                    data_point = apply_devcode_transformations(
                        devcode, data_point.copy()
                    )

                value = data_point.get("val")

                # Handle enum types (priorities, modes, etc.)
                if self._sensor_config.get("device_class") == "enum":
                    if value is not None and value != "":
                        return str(value)
                    return "Unknown"

                # Handle numeric types (voltage, current)
                if self._sensor_config.get("device_class") in ["voltage", "current"]:
                    try:
                        return float(value) if value is not None else None
                    except (ValueError, TypeError):
                        return None

                return value

        return None

    def _build_enum_options(self, sensor_config: dict[str, Any]) -> list[str]:
        """Return enum options aligned with device-specific transformations."""
        options = [str(option) for option in sensor_config.get("options", [])]
        device_meta = self._device_meta
        devcode = device_meta.get("devcode") if isinstance(device_meta, dict) else None

        if not devcode or not options:
            return options

        transformed_options: set[str] = set()
        for option in options:
            mapped = option
            key = self._sensor_key.lower()
            if key == "output priority":
                mapped = map_output_priority(devcode, option)
            elif key == "charger source priority":
                mapped = map_charger_priority(devcode, option)
            if mapped:
                transformed_options.add(str(mapped))

        transformed_options.update(options)
        return sorted(transformed_options)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self._device_sn in self.coordinator.data
        )
