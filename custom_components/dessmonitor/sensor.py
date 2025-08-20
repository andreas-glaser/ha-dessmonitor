"""Platform for DessMonitor sensor integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (SensorDeviceClass, SensorEntity,
                                             SensorStateClass)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DessMonitor sensors based on a config entry."""
    _LOGGER.debug(
        "Setting up DessMonitor sensors for config entry: %s", config_entry.entry_id
    )
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    entities = []

    if coordinator.data:
        _LOGGER.debug("Processing sensor data for %d devices", len(coordinator.data))

        for device_sn, device_info in coordinator.data.items():
            device_data = device_info.get("data", [])
            device_meta = device_info.get("device", {})
            collector_meta = device_info.get("collector", {})

            _LOGGER.debug(
                "Processing device %s with %d data points", device_sn, len(device_data)
            )

            seen_sensors = set()
            supported_sensors = 0
            duplicate_sensors = 0

            for data_point in device_data:
                sensor_type = data_point.get("title")
                if sensor_type in SENSOR_TYPES:
                    # Create unique key to prevent duplicates
                    sensor_key = f"{device_sn}_{sensor_type}"
                    if sensor_key not in seen_sensors:
                        seen_sensors.add(sensor_key)
                        entities.append(
                            DessMonitorSensor(
                                coordinator=coordinator,
                                device_sn=device_sn,
                                device_meta=device_meta,
                                collector_meta=collector_meta,
                                sensor_type=sensor_type,
                                data_point=data_point,
                            )
                        )
                        supported_sensors += 1
                        _LOGGER.debug(
                            "Created sensor: %s for device %s", sensor_type, device_sn
                        )
                    else:
                        duplicate_sensors += 1
                        _LOGGER.warning(
                            "Duplicate sensor detected: %s for device %s",
                            sensor_type,
                            device_sn,
                        )
                else:
                    _LOGGER.debug(
                        "Unsupported sensor type: %s for device %s",
                        sensor_type,
                        device_sn,
                    )

            _LOGGER.info(
                "Device %s: created %d sensors, skipped %d duplicates",
                device_sn,
                supported_sensors,
                duplicate_sensors,
            )
    else:
        _LOGGER.warning("No device data available for sensor setup")

    _LOGGER.info("Adding %d total sensors to Home Assistant", len(entities))
    async_add_entities(entities, True)


class DessMonitorSensor(CoordinatorEntity, SensorEntity):
    """Representation of a DessMonitor sensor."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
        sensor_type: str,
        data_point: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._sensor_type = sensor_type

        device_alias = device_meta.get("alias", "DessMonitor")
        sensor_config = SENSOR_TYPES.get(sensor_type, {})
        sensor_name = sensor_config.get("name", sensor_type)

        self._attr_name = f"{device_alias} {sensor_name}"

        # Create a more robust unique ID using the sensor config key instead of raw sensor type
        sensor_key = None
        for key, config in SENSOR_TYPES.items():
            if key == sensor_type:
                sensor_key = key
                break

        if sensor_key:
            unique_suffix = sensor_key.lower().replace(" ", "_").replace("-", "_")
        else:
            unique_suffix = sensor_type.lower().replace(" ", "_").replace("-", "_")

        self._attr_unique_id = f"{device_sn}_{unique_suffix}"

        _LOGGER.debug(
            "Initialized sensor: name='%s', unique_id='%s', device='%s', type='%s'",
            self._attr_name,
            self._attr_unique_id,
            device_sn,
            sensor_type,
        )

        sensor_config = SENSOR_TYPES[sensor_type]
        unit = sensor_config.get("unit", "")
        if unit == "W":
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_device_class = SensorDeviceClass.POWER
        elif unit == "V":
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
            self._attr_device_class = SensorDeviceClass.VOLTAGE
        elif unit == "A":
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
            self._attr_device_class = SensorDeviceClass.CURRENT
        elif unit == "Hz" or unit == "HZ":
            self._attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
            self._attr_device_class = SensorDeviceClass.FREQUENCY
        elif unit == "°C":
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        elif unit == "%":
            self._attr_native_unit_of_measurement = "%"
        else:
            self._attr_native_unit_of_measurement = unit

        if sensor_config.get("state_class"):
            if sensor_config["state_class"] == "measurement":
                self._attr_state_class = SensorStateClass.MEASUREMENT

        if sensor_config.get("icon"):
            self._attr_icon = sensor_config["icon"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        collector_pn = self._collector_meta.get("pn", "Unknown")
        device_alias = self._device_meta.get("alias")
        firmware = self._collector_meta.get("fireware", "Unknown")

        if not device_alias:
            device_name = f"Inverter {collector_pn}"
        else:
            device_name = f"{device_alias} ({collector_pn})"

        _LOGGER.debug(
            "Device info for %s: name='%s', pn='%s', firmware='%s'",
            self._device_sn,
            device_name,
            collector_pn,
            firmware,
        )

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_sn)},
            name=device_name,
            manufacturer="DessMonitor",
            model="Energy Storage Inverter",
            sw_version=firmware,
            serial_number=self._device_sn,
        )

    @property
    def native_value(self) -> str | float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            _LOGGER.debug(
                "No coordinator data available for sensor %s", self._attr_unique_id
            )
            return None

        device_info = self.coordinator.data.get(self._device_sn)
        if not device_info:
            _LOGGER.debug(
                "No device info found for device %s (sensor: %s)",
                self._device_sn,
                self._attr_unique_id,
            )
            return None

        device_data = device_info.get("data", [])

        for data_point in device_data:
            if data_point.get("title") == self._sensor_type:
                value = data_point.get("val")

                _LOGGER.debug(
                    "Raw value for sensor %s (%s): %s (type: %s)",
                    self._attr_unique_id,
                    self._sensor_type,
                    value,
                    type(value).__name__,
                )

                try:
                    if value is not None and value != "":
                        numeric_value = float(value)
                        _LOGGER.debug(
                            "Converted value for sensor %s: %s -> %s",
                            self._attr_unique_id,
                            value,
                            numeric_value,
                        )
                        return numeric_value
                    return value
                except (ValueError, TypeError) as e:
                    _LOGGER.debug(
                        "Could not convert value to float for sensor %s: %s (%s)",
                        self._attr_unique_id,
                        value,
                        e,
                    )
                    return str(value) if value is not None else None

        _LOGGER.debug(
            "No matching data point found for sensor %s (looking for: %s)",
            self._attr_unique_id,
            self._sensor_type,
        )
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return None

        device_info = self.coordinator.data.get(self._device_sn)
        if not device_info:
            return None

        device_data = device_info.get("data", [])

        attrs = {}
        for data_point in device_data:
            if data_point.get("title") == "Timestamp":
                attrs["last_updated"] = data_point.get("val")
            elif data_point.get("title") == "Operating mode":
                attrs["operating_mode"] = data_point.get("val")

        return attrs if attrs else None
