"""Platform for DessMonitor sensor integration."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import DOMAIN, SENSOR_TYPES, UNITS
from .device_support import apply_devcode_transformations
from .utils import create_device_info

_LOGGER = logging.getLogger(__name__)

ENUM_SENSOR_TITLES = {
    "Operating mode",
    "Output priority",
    "Charger Source Priority",
}

DIAGNOSTIC_SENSOR_TITLES = {
    "Output Voltage Setting",
    "Output priority",
    "Charger Source Priority",
}


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
                # Check original sensor type first (before transformations)
                original_sensor_type = data_point.get("title")

                if original_sensor_type in SENSOR_TYPES:
                    # Apply devcode-specific transformations after confirming it's a valid sensor
                    devcode = device_meta.get("devcode")
                    if devcode:
                        data_point = apply_devcode_transformations(
                            devcode, data_point.copy()
                        )

                    sensor_type = (
                        original_sensor_type  # Use original type for sensor creation
                    )
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
                        original_sensor_type,
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

        sensor_config: dict[str, Any] = cast(
            dict[str, Any], SENSOR_TYPES.get(sensor_type, {})
        )

        self._initialize_identity(sensor_config)
        self._apply_unit_metadata(sensor_config.get("unit", ""))
        self._apply_sensor_traits(sensor_config)

        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )

        _LOGGER.debug(
            "Initialized sensor: name='%s', unique_id='%s', device='%s', type='%s'",
            self._attr_name,
            self._attr_unique_id,
            device_sn,
            sensor_type,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self._attr_device_info

    def _initialize_identity(self, sensor_config: dict[str, Any]) -> None:
        """Initialise name and unique ID for the entity."""
        device_alias = self._device_meta.get("alias", "DessMonitor")
        sensor_name = sensor_config.get("name", self._sensor_type)
        self._attr_name = f"{device_alias} {sensor_name}"

        unique_suffix = self._build_unique_suffix(self._sensor_type)
        self._attr_unique_id = f"{self._device_sn}_{unique_suffix}"

    @staticmethod
    def _build_unique_suffix(sensor_type: str) -> str:
        """Create a consistent suffix for unique_id generation."""
        return sensor_type.lower().replace(" ", "_").replace("-", "_")

    def _apply_unit_metadata(self, unit: str) -> None:
        """Configure unit/device class metadata with sensible defaults."""
        native_unit, device_class, precision = self._unit_metadata_from_unit(unit)
        self._attr_native_unit_of_measurement = native_unit

        if device_class is not None:
            self._attr_device_class = device_class

        if precision is not None:
            self._attr_suggested_display_precision = precision

    @staticmethod
    def _unit_metadata_from_unit(
        unit: str,
    ) -> tuple[
        str
        | UnitOfPower
        | UnitOfEnergy
        | UnitOfElectricPotential
        | UnitOfElectricCurrent
        | UnitOfFrequency
        | UnitOfTemperature,
        SensorDeviceClass | None,
        int | None,
    ]:
        """Return (native_unit, device_class, precision) for a given unit string."""
        if unit == UNITS["POWER"]:
            return UnitOfPower.WATT, SensorDeviceClass.POWER, None
        if unit == UNITS["POWER_KW"]:
            return UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, None
        if unit == UNITS["ENERGY"]:
            return UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, None
        if unit == UNITS["VOLTAGE"]:
            return UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, 1
        if unit == UNITS["CURRENT"]:
            return UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, 1
        if unit in {UNITS["FREQUENCY"], "HZ"}:
            return UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, None
        if unit == UNITS["TEMPERATURE"]:
            return UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, None
        if unit == UNITS["PERCENTAGE"]:
            return UNITS["PERCENTAGE"], None, None
        if unit == UNITS["APPARENT_POWER"]:
            device_class = getattr(SensorDeviceClass, "APPARENT_POWER", None)
            return unit, device_class, None

        return unit, None, None

    def _apply_sensor_traits(self, sensor_config: dict[str, Any]) -> None:
        """Apply additional metadata such as state class and icons."""
        if sensor_config.get("device_class") == "enum":
            self._attr_device_class = SensorDeviceClass.ENUM
            if self._sensor_type == "Operating mode":
                from .device_support import get_all_operating_modes

                self._attr_options = get_all_operating_modes()

        state_class = sensor_config.get("state_class")
        if state_class == "measurement":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif state_class == "total_increasing":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        icon = sensor_config.get("icon")
        if icon:
            self._attr_icon = str(icon)

        if self._sensor_type in DIAGNOSTIC_SENSOR_TITLES:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            _LOGGER.debug(
                "Set entity category to DIAGNOSTIC for sensor %s", self._sensor_type
            )

    @property
    def native_value(self) -> str | float | None:
        """Return the state of the sensor."""
        device_payload = self._get_device_payload()
        if not device_payload:
            return None

        match = self._find_matching_data_point(device_payload)
        if not match:
            return None

        data_point, devcode = match
        value = self._extract_transformed_value(data_point, devcode)
        return self._coerce_native_value(value)

    def _get_device_payload(self) -> dict[str, Any] | None:
        """Return cached device payload for this sensor."""
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

        return device_info

    def _find_matching_data_point(
        self, device_payload: dict[str, Any]
    ) -> tuple[dict[str, Any], Any] | None:
        """Locate the matching data point for the current sensor."""
        device_data = device_payload.get("data", [])
        device_meta = device_payload.get("device", {})
        devcode = device_meta.get("devcode")

        for data_point in device_data:
            if data_point.get("title") == self._sensor_type:
                return data_point, devcode

        _LOGGER.debug(
            "No matching data point found for sensor %s (looking for: %s)",
            self._attr_unique_id,
            self._sensor_type,
        )
        return None

    def _extract_transformed_value(
        self, data_point: dict[str, Any], devcode: Any
    ) -> Any:
        """Apply devcode transformations and return the raw value."""
        working_point = data_point
        if devcode:
            working_point = apply_devcode_transformations(devcode, data_point.copy())

        value = working_point.get("val")
        _LOGGER.debug(
            "Raw value for sensor %s (%s): %s (type: %s)",
            self._attr_unique_id,
            self._sensor_type,
            value,
            type(value).__name__,
        )
        return value

    def _coerce_native_value(self, value: Any) -> str | float | None:
        """Coerce API value into Home Assistant native value format."""
        if self._sensor_type in ENUM_SENSOR_TITLES:
            return self._coerce_enum_value(value)
        return self._coerce_numeric_value(value)

    def _coerce_enum_value(self, value: Any) -> str:
        """Coerce enumerated values to strings with fallbacks."""
        if value is not None and value != "":
            return str(value)
        return "Unknown"

    def _coerce_numeric_value(self, value: Any) -> float | str | None:
        """Attempt to coerce sensor value into a float when possible."""
        if value in (None, ""):
            return value

        try:
            numeric_value = float(value)
            _LOGGER.debug(
                "Converted value for sensor %s: %s -> %s",
                self._attr_unique_id,
                value,
                numeric_value,
            )
            return numeric_value
        except (ValueError, TypeError) as err:
            _LOGGER.debug(
                "Could not convert value to float for sensor %s: %s (%s)",
                self._attr_unique_id,
                value,
                err,
            )
            return str(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return None

        device_info = self.coordinator.data.get(self._device_sn)
        if not device_info:
            return None

        device_data = device_info.get("data", [])
        device = device_info.get("device", {})
        devcode = device.get("devcode")

        attrs = {}
        for data_point in device_data:
            original_title = data_point.get("title")

            if original_title == "Timestamp":
                attrs["last_updated"] = data_point.get("val")
            elif original_title == "Operating mode":
                # Apply transformations for operating mode display value
                if devcode:
                    transformed_point = apply_devcode_transformations(
                        devcode, data_point.copy()
                    )
                    attrs["operating_mode"] = transformed_point.get("val")
                else:
                    attrs["operating_mode"] = data_point.get("val")

        return attrs if attrs else None
