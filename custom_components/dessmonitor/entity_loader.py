"""Shared recovery-aware loader for entities discovered after setup."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DessMonitorDataUpdateCoordinator

EntityBuilder = Callable[[], Awaitable[Sequence[Entity]]]


async def async_setup_dynamic_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    coordinator: DessMonitorDataUpdateCoordinator,
    async_add_entities: AddEntitiesCallback,
    builder: EntityBuilder,
    *,
    task_name: str,
    defer_initial: bool = False,
) -> None:
    """Load once, then retry only after a successful cloud-data revision."""
    task: asyncio.Task[None] | None = None
    loaded_revision = -1

    async def _load() -> None:
        nonlocal loaded_revision
        requested_revision = coordinator.cloud_revision
        try:
            entities = await builder()
            if entities:
                async_add_entities(entities)
        finally:
            # A local push does not advance this counter. A recovered cloud
            # refresh does, giving failed control discovery one bounded retry.
            loaded_revision = requested_revision
            if coordinator.cloud_revision != loaded_revision:
                # The cloud recovered while this potentially slow API scan was
                # in flight. Schedule after the current task reaches done so
                # the newer revision is not accidentally swallowed.
                asyncio.get_running_loop().call_soon(_schedule_load)

    @callback
    def _schedule_load() -> None:
        nonlocal task
        if coordinator.cloud_revision == loaded_revision:
            return
        if task is not None and not task.done():
            return
        task = hass.async_create_task(_load(), task_name)

    @callback
    def _cancel_task() -> None:
        if task is not None and not task.done():
            task.cancel()

    config_entry.async_on_unload(coordinator.async_add_listener(_schedule_load))
    config_entry.async_on_unload(_cancel_task)
    if defer_initial:
        _schedule_load()
    else:
        await _load()
