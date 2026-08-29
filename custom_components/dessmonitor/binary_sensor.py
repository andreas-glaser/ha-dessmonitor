"""Platform for DessMonitor binary sensor integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import BINARY_SENSOR_TYPES, DOMAIN
from .utils import create_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DessMonitor binary sensors based on a config entry."""
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    known_entities: set[str] = set()

    def _add_new_entities() -> None:
        entities = _build_binary_sensor_entities(coordinator, known_entities)
        if entities:
            # Coordinator data is already current; avoid an extra API refresh.
            async_add_entities(entities)

    _add_new_entities()
    config_entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


def _build_binary_sensor_entities(
    coordinator: DessMonitorDataUpdateCoordinator, known_entities: set[str]
) -> list[BinarySensorEntity]:
    """Build connectivity and binary sensors for newly discovered devices."""
    entities: list[BinarySensorEntity] = []
    if not isinstance(coordinator.data, dict):
        return entities

    for device_sn, device_info in coordinator.data.items():
        device_data = device_info.get("data", [])
        device_meta = device_info.get("device", {})
        collector_meta = device_info.get("collector", {})

        status_key = f"{device_sn}_status"
        if status_key not in known_entities:
            known_entities.add(status_key)
            entities.append(
                DessMonitorStatusSensor(
                    coordinator=coordinator,
                    device_sn=device_sn,
                    device_meta=device_meta,
                    collector_meta=collector_meta,
                )
            )

        for data_point in device_data:
            sensor_type = data_point.get("title")
            entity_key = f"{device_sn}_{sensor_type}_binary"
            if sensor_type in BINARY_SENSOR_TYPES and entity_key not in known_entities:
                known_entities.add(entity_key)
                entities.append(
                    DessMonitorBinarySensor(
                        coordinator=coordinator,
                        device_sn=device_sn,
                        device_meta=device_meta,
                        collector_meta=collector_meta,
                        sensor_type=sensor_type,
                    )
                )
    return entities


class DessMonitorBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a DessMonitor binary sensor."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
        sensor_type: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._sensor_type = sensor_type
        self._attr_name = f"{device_meta.get('alias', 'DessMonitor')} {BINARY_SENSOR_TYPES[sensor_type]['name']}"
        self._attr_unique_id = (
            f"{device_sn}_{sensor_type.lower().replace(' ', '_')}_binary"
        )

        sensor_config = BINARY_SENSOR_TYPES[sensor_type]
        if sensor_config.get("device_class"):
            self._attr_device_class = sensor_config["device_class"]

        if sensor_config.get("icon"):
            self._attr_icon = sensor_config["icon"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return create_device_info(
            self._device_sn, self._device_meta, self._collector_meta
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not self.coordinator.data:
            return None

        device_info = self.coordinator.data.get(self._device_sn)
        if not device_info:
            return None

        device_data = device_info.get("data", [])

        for data_point in device_data:
            if data_point.get("title") == self._sensor_type:
                value = data_point.get("val", "").lower()

                if self._sensor_type == "Operating mode":
                    return value not in ["off-grid mode", "off_grid"]

        return None


class DessMonitorStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a DessMonitor device status sensor."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
    ) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator)

        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._attr_name = f"{device_meta.get('alias', 'DessMonitor')} Status"
        self._attr_unique_id = f"{device_sn}_status"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_icon = "mdi:connection"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return create_device_info(
            self._device_sn, self._device_meta, self._collector_meta
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is online."""
        if not self.coordinator.data:
            return False

        device_info = self.coordinator.data.get(self._device_sn)
        if not device_info:
            return False

        device_data = device_info.get("data", [])
        return len(device_data) > 0

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
                attrs["last_seen"] = data_point.get("val")
            elif data_point.get("title") == "Operating mode":
                attrs["operating_mode"] = data_point.get("val")

        return attrs if attrs else None
