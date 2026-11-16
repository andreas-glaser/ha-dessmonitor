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
from .control_values import (
    TRANSPORT_CLOUD,
    cloud_control_snapshot,
    control_value,
    first_control_value,
    option_key_for,
)
from .device_support.device_registry import (
    control_value_reading,
    filter_control_options,
    map_control_field,
)
from .entity_loader import async_setup_dynamic_entities
from .utils import (
    async_migrate_control_unique_ids,
    control_entity_suffix,
    create_device_info,
)

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
        entities = await _async_build_select_entities(coordinator, known_entities)
        async_migrate_control_unique_ids(hass, config_entry, "select", entities)
        return entities

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
                    api_name=name,
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
        api_name: str | None = None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._param_name = name
        self._api_name = api_name or name
        self._param_id = param_id
        self._control_transport = TRANSPORT_CLOUD
        self._last_cloud_sample: object = None

        # Titles whose reading carries this control's value, most specific
        # first. A profile adds one where the collector answers the control's
        # own name with a live measurement rather than the setting (#61).
        declared = control_value_reading(device_meta.get("devcode"), param_id)
        self._value_titles: tuple[str, ...] = tuple(
            title for title in (declared, self._api_name, self._param_name) if title
        )

        self._all_options = dict(options_map)
        self._current_value = initial_value
        self._options_error: str | None = None

        # Initialize identity
        device_alias = device_meta.get("alias", "DessMonitor")
        self._attr_name = f"{device_alias} {name}"
        self._attr_unique_id = f"{device_sn}_{control_entity_suffix(name)}"
        self._legacy_unique_id = f"{device_sn}_{control_entity_suffix(self._api_name)}"
        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )
        self._attr_entity_category = EntityCategory.CONFIG

        self._refresh_options()

    @property
    def legacy_unique_id(self) -> str:
        """Return the unique id this control carried before its name changed."""
        return self._legacy_unique_id

    @property
    def available(self) -> bool:
        """Keep a control unavailable until its options can be safely determined."""
        return super().available and bool(self._attr_options)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Say which transport last carried a write for this control."""
        return {
            "control_transport": self._control_transport,
            "value_status": (
                "last_known" if self.current_option is not None else "not_loaded"
            ),
        }

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
        """Recover current values without treating a local push as a cloud read."""
        coordinator = cast(DessMonitorDataUpdateCoordinator, self.coordinator)
        stamp, points = cloud_control_snapshot(coordinator, self._device_sn)
        cached = coordinator.ctrl_value_cache.get(self._device_sn, {})
        value = control_value(cached.get(self._param_id))
        if stamp != self._last_cloud_sample:
            self._last_cloud_sample = stamp
            value = first_control_value(points, *self._value_titles) or value
        if value is not None:
            # A vendor may report a setting in a spelling it does not offer,
            # such as 60.0 for an option keyed "60.00". The option's own key is
            # what a write has to send, so that is what is kept.
            matched = option_key_for(self._all_options, value)
            if matched is not None:
                self._current_value = (
                    value
                    if value in self._all_options or value in self._all_options.values()
                    else matched
                )
                if self._device_sn in coordinator.ctrl_value_cache:
                    cached[self._param_id] = self._current_value
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

        try:
            result = await coordinator.async_set_control_value(
                self._device_sn,
                self._param_id,
                api_value,
                control_name=self._param_name,
            )
            self._current_value = option
            self._control_transport = result.transport
            self._last_cloud_sample = cloud_control_snapshot(
                coordinator, self._device_sn
            )[0]
            self._attr_current_option = option
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set option for %s: %s", self._attr_unique_id, err)
            raise
