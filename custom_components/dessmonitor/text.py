"""A validated, timezone-free inverter clock control."""

from __future__ import annotations

import re
from datetime import datetime

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .temporal_controls import (
    DessMonitorTemporalControl,
    async_setup_temporal_platform,
)

_CLOCK_PATTERN = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2} (?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose the inverter's wall clock without assuming it uses HA's timezone."""
    await async_setup_temporal_platform(
        hass, config_entry, async_add_entities, "text", DessMonitorClock
    )


class DessMonitorClock(DessMonitorTemporalControl, TextEntity):
    """Keep the API's calendar string; DateTimeEntity would require a known zone."""

    value_format = "YYYY-MM-DD HH:MM:SS"
    _attr_native_min = 19
    _attr_native_max = 19
    _attr_pattern = f"^{_CLOCK_PATTERN}$"
    _attr_icon = "mdi:calendar-clock"

    def _parse_value(self, raw: str | None) -> str | None:
        if raw is None or not re.fullmatch(_CLOCK_PATTERN, raw):
            return None
        try:
            datetime.fromisoformat(raw)
        except ValueError:
            return None
        return raw

    async def async_set_value(self, value: str) -> None:
        """Validate the actual calendar date before forwarding the literal string."""
        await self._async_write_value(value)
