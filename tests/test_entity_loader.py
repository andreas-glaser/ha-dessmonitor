"""Tests for recovery-aware dynamic cloud entity discovery."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.dessmonitor.entity_loader import async_setup_dynamic_entities


async def test_loader_retries_on_cloud_recovery_but_not_local_pushes(
    hass: HomeAssistant,
) -> None:
    """Five-second local updates cannot cause repeated API control discovery."""
    coordinator = MagicMock()
    coordinator.cloud_revision = 0
    listeners = []
    coordinator.async_add_listener.side_effect = lambda listener: (
        listeners.append(listener) or MagicMock()
    )
    entry = MagicMock()
    builder = AsyncMock(return_value=[])
    add_entities = MagicMock()

    await async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        add_entities,
        builder,
        task_name="test_dynamic_discovery",
    )
    assert builder.await_count == 1
    assert len(listeners) == 1

    listeners[0]()
    await hass.async_block_till_done()
    assert builder.await_count == 1

    coordinator.cloud_revision = 1
    listeners[0]()
    await hass.async_block_till_done()
    assert builder.await_count == 2

    listeners[0]()
    await hass.async_block_till_done()
    assert builder.await_count == 2


async def test_loader_can_defer_slow_control_discovery(
    hass: HomeAssistant,
) -> None:
    """Cached/local telemetry setup is not blocked by slow API controls."""
    coordinator = MagicMock(cloud_revision=0)
    coordinator.async_add_listener.return_value = MagicMock()
    entry = MagicMock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_builder() -> list:
        started.set()
        await release.wait()
        return []

    await async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        MagicMock(),
        _slow_builder,
        task_name="test_deferred_discovery",
        defer_initial=True,
    )
    await started.wait()
    release.set()
    await hass.async_block_till_done()


async def test_loader_retries_revision_that_arrives_during_slow_scan(
    hass: HomeAssistant,
) -> None:
    """Cloud recovery in flight immediately retries missing control entities."""
    coordinator = MagicMock(cloud_revision=0)
    listeners = []
    coordinator.async_add_listener.side_effect = lambda listener: (
        listeners.append(listener) or MagicMock()
    )
    entry = MagicMock()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def _builder() -> list:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
        return []

    await async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        MagicMock(),
        _builder,
        task_name="test_inflight_recovery",
        defer_initial=True,
    )
    await started.wait()
    coordinator.cloud_revision = 1
    listeners[0]()
    release.set()
    await hass.async_block_till_done()

    assert calls == 2
