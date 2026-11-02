"""Minute-resolution cloud schedule controls for devcode 6544."""

from __future__ import annotations

import re
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .temporal_controls import (
    DessMonitorTemporalControl,
    async_setup_temporal_platform,
)

_TIME_RE = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up advertised schedule fields, sharing the cloud controls cache."""
    await async_setup_temporal_platform(
        hass, config_entry, async_add_entities, "time", DessMonitorTime
    )


class DessMonitorTime(DessMonitorTemporalControl, TimeEntity):
    """A daily inverter-local schedule boundary, with no timezone conversion."""

    value_format = "HH:MM"

    def _parse_value(self, raw: str | None) -> time | None:
        if raw is None or not _TIME_RE.fullmatch(raw):
            return None
        try:
            return time.fromisoformat(raw)
        except ValueError:
            return None

    async def async_set_value(self, value: time) -> None:
        """Write exact minutes; do not silently discard seconds or timezone info."""
        if value.tzinfo is not None or value.second or value.microsecond:
            raise ValueError("Schedule time requires local HH:MM with zero seconds")
        await self._async_write_value(value.isoformat(timespec="minutes"))
