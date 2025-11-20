"""Platform for DessMonitor number entities."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import DOMAIN
from .device_support.device_registry import map_control_field
from .utils import create_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DessMonitor number entities based on a config entry."""
    _LOGGER.debug(
        "Setting up DessMonitor number entities for config entry: %s",
        config_entry.entry_id,
    )
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    if not coordinator.data:
        _LOGGER.debug("No coordinator data available; skipping number setup")
        return

    coordinator_data = cast(dict[str, dict[str, Any]], coordinator.data)
    entities = []

    for device_sn, raw_device_info in coordinator_data.items():
        device_info = cast(dict[str, Any], raw_device_info)
        device_meta = device_info.get("device", {})
        collector_meta = device_info.get("collector", {})
        pn = collector_meta.get("pn")
        devcode = device_meta.get("devcode")
        devaddr = device_meta.get("devaddr")

        if not all([pn, devcode, devaddr]):
            _LOGGER.debug(
                "Missing device identity info for %s (pn=%s, devcode=%s, devaddr=%s); skipping controls",
                device_sn,
                pn,
                devcode,
                devaddr,
            )
            continue

        try:
            controls = await coordinator.api.get_device_control_fields(
                pn, devcode, devaddr, device_sn
            )
        except Exception as err:
            _LOGGER.warning(
                "Failed to fetch control fields for device %s: %s", device_sn, err
            )
            continue

        try:
            current_params = await coordinator.api.get_device_parameters(
                pn, devcode, devaddr, device_sn
            )
        except Exception as err:
            _LOGGER.warning(
                "Failed to fetch current parameters for device %s: %s", device_sn, err
            )
            current_params = {}

        for name, config in controls.items():
            if config.get("type") != "value":
                continue

            param_id = config.get("id")
            if not param_id:
                continue

            # Apply control field mapping
            friendly_name = map_control_field(devcode, name)

            entities.append(
                DessMonitorNumber(
                    coordinator,
                    device_sn,
                    device_meta,
                    collector_meta,
                    friendly_name,
                    param_id,
                    current_params.get(name, {}).get("value"),
                    current_params.get(name, {}).get("unit"),
                )
            )

    if entities:
        _LOGGER.info("Adding %d number entities", len(entities))
        async_add_entities(entities)


class DessMonitorNumber(CoordinatorEntity, NumberEntity):
    """Representation of a DessMonitor number entity."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
        name: str,
        param_id: str,
        initial_value: str | float | None,
        unit: str | None,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._param_name = name
        self._param_id = param_id
        self._attr_native_unit_of_measurement = unit

        # Initialize identity
        device_alias = device_meta.get("alias", "DessMonitor")
        self._attr_name = f"{device_alias} {name}"
        unique_suffix = name.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{device_sn}_{unique_suffix}"
        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )
        self._attr_entity_category = EntityCategory.CONFIG

        # Set initial state if available
        if initial_value is not None:
            try:
                self._attr_native_value = float(initial_value)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Could not convert initial value '%s' to float for %s",
                    initial_value,
                    self._attr_unique_id,
                )

        # Guess min/max based on unit/name if possible, otherwise use generous defaults
        # These defaults might need tuning based on specific parameter types
        if unit == "V":
            self._attr_native_min_value = 0
            self._attr_native_max_value = 500
            self._attr_native_step = 0.1
        elif unit == "A":
            self._attr_native_min_value = 0
            self._attr_native_max_value = 200
            self._attr_native_step = 0.1
        elif unit == "%":
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100
            self._attr_native_step = 1
        else:
            self._attr_native_min_value = 0
            self._attr_native_max_value = 1000
            self._attr_native_step = 1

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        _LOGGER.debug("Setting %s to %s", self._attr_unique_id, value)

        device = self.coordinator.data.get(self._device_sn, {}).get("device", {})
        collector = self.coordinator.data.get(self._device_sn, {}).get("collector", {})

        try:
            await self.coordinator.api.set_device_control_value(
                pn=collector.get("pn"),
                devcode=device.get("devcode"),
                devaddr=device.get("devaddr"),
                sn=self._device_sn,
                param_id=self._param_id,
                value=str(value),
            )
            self._attr_native_value = value
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set value for %s: %s", self._attr_unique_id, err)
            raise
