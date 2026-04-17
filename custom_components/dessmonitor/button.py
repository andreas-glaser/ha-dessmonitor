"""Platform for DessMonitor button entities."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.button import ButtonEntity
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
    """Set up DessMonitor button entities based on a config entry."""
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    if not coordinator.data:
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

        controls, _ = await coordinator.async_get_controls_with_values(
            pn, devcode, devaddr, device_sn
        )

        for name, config in controls.items():
            if config.get("type") != "options":
                continue

            options_map = config.get("options", {})
            if len(options_map) != 1:
                continue

            param_id = config.get("id")
            if not param_id:
                continue

            api_value = next(iter(options_map.keys()))
            friendly_name = map_control_field(devcode, name)

            entities.append(
                DessMonitorButton(
                    coordinator,
                    device_sn,
                    device_meta,
                    collector_meta,
                    friendly_name,
                    param_id,
                    api_value,
                )
            )

    if entities:
        _LOGGER.info("Adding %d button entities", len(entities))
        async_add_entities(entities)


class DessMonitorButton(CoordinatorEntity, ButtonEntity):
    """Representation of a DessMonitor button entity."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
        name: str,
        param_id: str,
        api_value: str,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._param_id = param_id
        self._api_value = api_value

        device_alias = device_meta.get("alias", "DessMonitor")
        self._attr_name = f"{device_alias} {name}"
        unique_suffix = name.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{device_sn}_{unique_suffix}"
        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Pressing %s (param %s)", self._attr_unique_id, self._param_id)

        device = self.coordinator.data.get(self._device_sn, {}).get("device", {})
        collector = self.coordinator.data.get(self._device_sn, {}).get("collector", {})

        await self.coordinator.api.set_device_control_value(
            pn=collector.get("pn"),
            devcode=device.get("devcode"),
            devaddr=device.get("devaddr"),
            sn=self._device_sn,
            param_id=self._param_id,
            value=self._api_value,
        )
