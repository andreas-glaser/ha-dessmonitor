"""Platform for DessMonitor number entities."""

from __future__ import annotations

import logging
import math
import re
from typing import Any, cast

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import DOMAIN
from .device_support.device_registry import map_control_field
from .number_range import compute_range_and_step, is_hint_range_usable
from .utils import create_device_info

_LOGGER = logging.getLogger(__name__)

_NUMBER_WITH_OPTIONAL_UNIT_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*[^\d]*$"
)


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

        if not pn or devcode is None or devaddr is None:
            _LOGGER.debug(
                "Missing device identity info for %s; skipping controls",
                device_sn,
            )
            continue

        controls, current_values = await coordinator.async_get_controls_with_values(
            pn, devcode, devaddr, device_sn
        )

        for name, config in controls.items():
            if config.get("type") != "value":
                continue

            param_id = config.get("id")
            if not param_id:
                continue

            friendly_name = map_control_field(devcode, name)

            entities.append(
                DessMonitorNumber(
                    coordinator,
                    device_sn,
                    device_meta,
                    collector_meta,
                    friendly_name,
                    name,
                    param_id,
                    current_values.get(param_id),
                    config.get("unit"),
                    config.get("hint"),
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
        api_name: str,
        param_id: str,
        initial_value: str | float | None,
        unit: str | None,
        hint: str | None,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._param_name = name
        self._api_name = api_name
        self._param_id = param_id
        self._hint = hint
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

        # Parse the current value before evaluating the API range hint.
        current_value = self._coerce_value(initial_value)
        if not is_hint_range_usable(hint, current_value):
            # An uncertain or broad fallback is much easier and safer to use as
            # a text box than as a large slider.
            self._attr_mode = NumberMode.BOX

        if current_value is not None:
            self._attr_native_value = current_value
        elif initial_value is not None:
            _LOGGER.warning(
                "Could not convert initial value '%s' to float for %s",
                initial_value,
                self._attr_unique_id,
            )

        self._apply_range_and_step(hint, current_value)

    @staticmethod
    def _coerce_value(raw: str | float | None) -> float | None:
        """Parse a control value (e.g. '57.6V') into a float, or None."""
        if raw is None:
            return None
        match = _NUMBER_WITH_OPTIONAL_UNIT_RE.match(str(raw))
        if not match:
            return None
        try:
            value = float(match.group(1))
        except (ValueError, TypeError):
            return None
        return value if math.isfinite(value) else None

    def _apply_range_and_step(self, hint: str | None, value: float | None) -> None:
        """Set min/max/step from the API hint, unit, and current value."""
        lo, hi, step = compute_range_and_step(
            self._attr_native_unit_of_measurement,
            hint,
            value,
        )
        if lo is not None:
            self._attr_native_min_value = lo
        if hi is not None:
            self._attr_native_max_value = hi
        self._attr_native_step = step

    def _value_from_coordinator(self) -> float | None:
        """Read this control from the regular polled device payload when present."""
        coordinator = cast(DessMonitorDataUpdateCoordinator, self.coordinator)
        device_info = coordinator.data.get(self._device_sn, {})
        source_names = {
            self._api_name.strip().casefold(),
            self._param_name.strip().casefold(),
        }

        for data_point in device_info.get("data", []):
            title = data_point.get("title")
            if isinstance(title, str) and title.strip().casefold() in source_names:
                return self._coerce_value(data_point.get("val"))
        return None

    def _expand_range_to_include(self, value: float) -> None:
        """Expand a heuristic range when a newly polled value falls outside it."""
        current_min = getattr(self, "_attr_native_min_value", None)
        current_max = getattr(self, "_attr_native_max_value", None)
        if (current_min is None or value >= current_min) and (
            current_max is None or value <= current_max
        ):
            return

        new_min, new_max, _ = compute_range_and_step(
            self._attr_native_unit_of_measurement, self._hint, value
        )
        if new_min is not None:
            self._attr_native_min_value = (
                new_min if current_min is None else min(current_min, new_min)
            )
        if new_max is not None:
            self._attr_native_max_value = (
                new_max if current_max is None else max(current_max, new_max)
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh controls also exposed in the normal polled payload."""
        value = self._value_from_coordinator()
        if value is not None:
            self._attr_native_value = value
            if not is_hint_range_usable(self._hint, value):
                self._attr_mode = NumberMode.BOX
            self._expand_range_to_include(value)

            coordinator = cast(DessMonitorDataUpdateCoordinator, self.coordinator)
            if self._device_sn in coordinator.ctrl_value_cache:
                coordinator.ctrl_value_cache[self._device_sn][self._param_id] = str(
                    value
                )

        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        if not math.isfinite(value):
            raise ValueError("Control value must be a finite number")

        _LOGGER.debug("Setting %s to %s", self._attr_unique_id, value)

        coordinator = cast(DessMonitorDataUpdateCoordinator, self.coordinator)
        device = coordinator.data.get(self._device_sn, {}).get("device", {})
        collector = coordinator.data.get(self._device_sn, {}).get("collector", {})

        try:
            await coordinator.api.set_device_control_value(
                pn=collector.get("pn"),
                devcode=device.get("devcode"),
                devaddr=device.get("devaddr"),
                sn=self._device_sn,
                param_id=self._param_id,
                value=str(value),
            )
            self._attr_native_value = value
            if self._device_sn in coordinator.ctrl_value_cache:
                coordinator.ctrl_value_cache[self._device_sn][self._param_id] = str(
                    value
                )
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set value for %s: %s", self._attr_unique_id, err)
            raise
