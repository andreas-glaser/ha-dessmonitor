"""Platform for DessMonitor select entities."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.select import SelectEntity
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
    """Set up DessMonitor select entities based on a config entry."""
    _LOGGER.debug(
        "Setting up DessMonitor select entities for config entry: %s",
        config_entry.entry_id,
    )
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    if not coordinator.data:
        _LOGGER.debug("No coordinator data available; skipping select setup")
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
            continue

        controls, current_values = await coordinator.async_get_controls_with_values(
            pn, devcode, devaddr, device_sn
        )

        for name, config in controls.items():
            if config.get("type") != "options":
                continue

            param_id = config.get("id")
            options_map = config.get("options", {})

            if not param_id or not options_map:
                continue

            friendly_name = map_control_field(devcode, name)

            entities.append(
                DessMonitorSelect(
                    coordinator,
                    device_sn,
                    device_meta,
                    collector_meta,
                    friendly_name,
                    param_id,
                    options_map,
                    current_values.get(param_id),
                )
            )

    if entities:
        _LOGGER.info("Adding %d select entities", len(entities))
        async_add_entities(entities)


class DessMonitorSelect(CoordinatorEntity, SelectEntity):
    """Representation of a DessMonitor select entity."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
        name: str,
        param_id: str,
        options_map: dict[str, str],
        initial_value: str | None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._param_name = name
        self._param_id = param_id

        # Store mapping of API key -> display string and reverse
        self._value_to_option = options_map
        self._option_to_value = {v: k for k, v in options_map.items()}

        self._attr_options = list(options_map.values())

        # Initialize identity
        device_alias = device_meta.get("alias", "DessMonitor")
        self._attr_name = f"{device_alias} {name}"
        unique_suffix = name.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{device_sn}_{unique_suffix}"
        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )
        self._attr_entity_category = EntityCategory.CONFIG

        # Set initial state from cached control value
        if initial_value is not None:
            if initial_value in self._attr_options:
                self._attr_current_option = initial_value
            else:
                mapped = self._value_to_option.get(str(initial_value))
                if mapped:
                    self._attr_current_option = mapped

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        api_value = self._option_to_value.get(option)
        if api_value is None:
            raise ValueError(f"Invalid option: {option}")

        _LOGGER.debug(
            "Setting %s to %s (API: %s)", self._attr_unique_id, option, api_value
        )

        device = self.coordinator.data.get(self._device_sn, {}).get("device", {})
        collector = self.coordinator.data.get(self._device_sn, {}).get("collector", {})

        try:
            await self.coordinator.api.set_device_control_value(
                pn=collector.get("pn"),
                devcode=device.get("devcode"),
                devaddr=device.get("devaddr"),
                sn=self._device_sn,
                param_id=self._param_id,
                value=api_value,
            )
            self._attr_current_option = option
            if self._device_sn in self.coordinator.ctrl_value_cache:
                self.coordinator.ctrl_value_cache[self._device_sn][
                    self._param_id
                ] = option
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set option for %s: %s", self._attr_unique_id, err)
            raise
