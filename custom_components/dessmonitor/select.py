"""Platform for DessMonitor select entities."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import DOMAIN
from .device_support.device_registry import filter_control_options, map_control_field
from .entity_loader import async_setup_dynamic_entities
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
    known_entities: set[str] = set()

    async def _build() -> list[SelectEntity]:
        return await _async_build_select_entities(coordinator, known_entities)

    await async_setup_dynamic_entities(
        hass,
        config_entry,
        coordinator,
        async_add_entities,
        _build,
        task_name="dessmonitor_select_discovery",
        # The API exposes control values one field at a time. Discover them in
        # the background so dozens of reads cannot delay integration startup.
        defer_initial=True,
    )


async def _async_build_select_entities(
    coordinator: DessMonitorDataUpdateCoordinator,
    known_entities: set[str],
) -> list[SelectEntity]:
    """Build cloud-backed selects not already registered by this platform."""

    if not coordinator.data:
        _LOGGER.debug("No coordinator data available; skipping select setup")
        return []

    coordinator_data = cast(dict[str, dict[str, Any]], coordinator.data)
    entities: list[SelectEntity] = []

    for device_sn, raw_device_info in coordinator_data.items():
        device_info = cast(dict[str, Any], raw_device_info)
        device_meta = device_info.get("device", {})
        collector_meta = device_info.get("collector", {})
        pn = collector_meta.get("pn")
        devcode = device_meta.get("devcode")
        devaddr = device_meta.get("devaddr")

        if not pn or devcode is None or devaddr is None:
            continue

        controls, current_values = await coordinator.async_get_controls_with_values(
            pn, devcode, devaddr, device_sn
        )

        for name, config in controls.items():
            if config.get("type") != "options":
                continue

            param_id = config.get("id")
            options_map = config.get("options", {})

            if not param_id or len(options_map) < 2:
                continue

            friendly_name = map_control_field(devcode, name)
            entity_key = f"{device_sn}:{param_id}"
            if entity_key in known_entities:
                continue

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
            known_entities.add(entity_key)

    if entities:
        _LOGGER.info("Adding %d select entities", len(entities))
    return entities


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

        self._all_options = dict(options_map)
        self._current_value = initial_value
        self._options_error: str | None = None

        # Initialize identity
        device_alias = device_meta.get("alias", "DessMonitor")
        self._attr_name = f"{device_alias} {name}"
        unique_suffix = name.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{device_sn}_{unique_suffix}"
        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )
        self._attr_entity_category = EntityCategory.CONFIG

        self._refresh_options()

    @property
    def available(self) -> bool:
        """Keep a control unavailable until its options can be safely determined."""
        return super().available and bool(self._attr_options)

    def _refresh_options(self) -> None:
        coordinator = cast(DessMonitorDataUpdateCoordinator, self.coordinator)
        device_info = coordinator.data.get(self._device_sn, {})
        devcode = self._device_meta["devcode"]
        try:
            options = filter_control_options(
                devcode, self._param_id, self._all_options, device_info.get("data", [])
            )
        except ValueError as err:
            reason = str(err)
            if reason != self._options_error:
                _LOGGER.warning(
                    "Control %s for devcode %s is unavailable: %s",
                    self._param_id,
                    devcode,
                    reason,
                )
            self._options_error = reason
            options = {}
        else:
            self._options_error = None
        self._option_to_value = {label: key for key, label in options.items()}
        self._attr_options = list(options.values())
        self._attr_current_option = None
        if self._current_value is not None:
            self._attr_current_option = (
                self._current_value
                if self._current_value in self._attr_options
                else options.get(str(self._current_value))
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Reevaluate options when rated metadata arrives or changes."""
        self._refresh_options()
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        coordinator = cast(DessMonitorDataUpdateCoordinator, self.coordinator)
        # A service call may arrive before the latest coordinator notification.
        self._refresh_options()
        api_value = self._option_to_value.get(option)
        if api_value is None:
            raise ValueError(f"Invalid option: {option}")

        _LOGGER.debug(
            "Setting %s to %s (API: %s)", self._attr_unique_id, option, api_value
        )

        device = coordinator.data.get(self._device_sn, {}).get("device", {})
        collector = coordinator.data.get(self._device_sn, {}).get("collector", {})

        try:
            await coordinator.api.set_device_control_value(
                pn=collector.get("pn"),
                devcode=device.get("devcode"),
                devaddr=device.get("devaddr"),
                sn=self._device_sn,
                param_id=self._param_id,
                value=api_value,
            )
            self._current_value = option
            self._attr_current_option = option
            if self._device_sn in coordinator.ctrl_value_cache:
                coordinator.ctrl_value_cache[self._device_sn][self._param_id] = option
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set option for %s: %s", self._attr_unique_id, err)
            raise
