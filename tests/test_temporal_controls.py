"""Verify wall-clock serialization, recovery, and numeric-entity replacement."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import time, timezone
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor import (
    MAX_CONTROL_VALUE_RETRIES,
    DessMonitorDataUpdateCoordinator,
)
from custom_components.dessmonitor.api import DessMonitorError
from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.number import _async_build_number_entities
from custom_components.dessmonitor.temporal_controls import (
    async_build_temporal_entities,
    disable_replaced_numbers,
)
from custom_components.dessmonitor.text import DessMonitorClock
from custom_components.dessmonitor.time import DessMonitorTime

FIELDS = {
    "Secondary Charging Priority Start Time": ("bat_eybond_read_43988", "15:00"),
    "Secondary Charging Priority End Time": ("bat_eybond_read_43989", "20:00"),
    "Secondary Output Priority Start Time": ("bse_eybond_read_43979", "15:30"),
    "Secondary Output Priority End Time": ("bse_eybond_read_43980", "17:00"),
    " Inverter Date": ("sys_eybond_read_44023", "2026-10-13 13:36:16"),
}


def _coordinator(hass, *, devcode=6544, values=True):
    api = AsyncMock()
    api.get_device_control_fields.return_value = {
        name: {"type": "value", "id": field_id}
        for name, (field_id, _) in FIELDS.items()
    }
    api.get_device_control_value.return_value = {"val": "null"}
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    data = {
        "TEST": {
            "device": {"devcode": devcode, "devaddr": 1, "alias": "Inverter"},
            "collector": {"pn": "PN"},
            "data": [
                {"title": "Timestamp", "val": "first"},
                *(
                    [{"title": name, "val": raw} for name, (_, raw) in FIELDS.items()]
                    if values
                    else []
                ),
            ],
        }
    }
    coordinator.cloud_revision = 1
    coordinator._cached_cloud_data = deepcopy(data)
    coordinator.async_set_updated_data(data)
    return coordinator


async def _entities(coordinator, kind="time", known=None):
    return await async_build_temporal_entities(
        coordinator,
        set() if known is None else known,
        kind,
        DessMonitorTime if kind == "time" else DessMonitorClock,
    )


@pytest.mark.parametrize("devcode", [6544, "6544"])
async def test_verified_fields_replace_numbers_without_extra_cloud_reads(hass, devcode):
    coordinator = _coordinator(hass, devcode=devcode)
    try:
        known = set()
        times = await _entities(coordinator, known=known)
        clocks = await _entities(coordinator, "text")
        assert [entity.native_value for entity in times] == [
            time(15),
            time(20),
            time(15, 30),
            time(17),
        ]
        assert clocks[0].native_value == "2026-10-13 13:36:16"
        assert await _async_build_number_entities(coordinator, set()) == []
        assert await _entities(coordinator, known=known) == []
        coordinator.api.get_device_control_fields.assert_awaited_once()
        coordinator.api.get_device_control_value.assert_not_awaited()
        coordinator.api.set_device_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_other_devcodes_and_unrelated_value_fields_remain_numeric(hass):
    coordinator = _coordinator(hass, devcode=2376)
    try:
        assert await _entities(coordinator) == []
        assert await _entities(coordinator, "text") == []
        assert len(await _async_build_number_entities(coordinator, set())) == 5
        coordinator.data["TEST"]["device"]["devcode"] = 6544
        coordinator.ctrl_field_cache["TEST"] = {
            "Charge duration": {"id": "duration", "type": "value", "unit": "Min"}
        }
        coordinator.ctrl_value_cache["TEST"] = {"duration": "120"}
        numbers = await _async_build_number_entities(coordinator, set())
        assert len(numbers) == 1 and numbers[0].native_value == 120
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,raw", [("time", "00:00"), ("text", "2028-02-29 23:59:59")]
)
async def test_exact_wire_values_and_failed_write_preserves_state(hass, kind, raw):
    coordinator = _coordinator(hass)
    entity = (await _entities(coordinator, kind))[0]
    new_value = time.fromisoformat(raw) if kind == "time" else raw
    original = entity.native_value
    cache = deepcopy(coordinator.ctrl_value_cache)
    try:
        with patch.object(entity, "async_write_ha_state"):
            coordinator.api.set_device_control_value.side_effect = DessMonitorError(
                "offline"
            )
            with pytest.raises(DessMonitorError):
                await entity.async_set_value(new_value)
            assert entity.native_value == original
            assert coordinator.ctrl_value_cache == cache
            assert coordinator.api.set_device_control_value.await_count == 1
            coordinator.api.set_device_control_value.side_effect = None
            await entity.async_set_value(new_value)
            coordinator.api.set_device_control_value.assert_awaited_with(
                pn="PN",
                devcode=6544,
                devaddr=1,
                sn="TEST",
                param_id=entity._field_id,
                value=raw,
            )
            assert entity.native_value == new_value
            # Fast local pushes and repeated cloud timestamps cannot replay old values.
            for _ in range(3):
                coordinator.data["TEST"]["data"][0]["val"] = "local-time"
                entity._handle_coordinator_update()
            assert entity.native_value == new_value
            assert entity.extra_state_attributes["time_basis"] == "inverter_wall_clock"
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,value",
    [
        ("time", time(15, 30, 1)),
        ("time", time(15, 30, microsecond=1)),
        ("time", time(15, 30, tzinfo=timezone.utc)),
        ("text", "2026-02-29 12:00:00"),
        ("text", "2026-10-13 24:00:00"),
        ("text", "2026-10-13T12:00:00Z"),
        ("text", "2026-10-13 12:00:00+03:00"),
        ("text", "2026-1-3 12:00:00"),
        ("text", "2026-10-13 12:00:00\n"),
    ],
)
async def test_invalid_writes_are_rejected_before_api(hass, kind, value):
    coordinator = _coordinator(hass)
    try:
        entity = (await _entities(coordinator, kind))[0]
        with pytest.raises(ValueError):
            await entity.async_set_value(value)
        coordinator.api.set_device_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,raw,bad",
    [
        ("time", "23:59", "24:00"),
        ("text", "2028-02-29 23:59:59", "2026-02-29 23:59:59"),
    ],
)
async def test_missing_values_recover_existing_entities_and_keep_last_known(
    hass, kind, raw, bad
):
    coordinator = _coordinator(hass, values=False)
    known = set()
    entity = (await _entities(coordinator, kind, known))[0]
    try:
        assert entity.native_value is None
        assert entity.extra_state_attributes["value_status"] == "not_loaded"
        initial_reads = coordinator.api.get_device_control_value.await_count
        await _entities(coordinator, kind, known)
        assert coordinator.api.get_device_control_value.await_count == initial_reads
        coordinator.cloud_revision += 1

        async def read(_pn, _code, _addr, _sn, field):
            return {"val": raw if field == entity._field_id else "null"}

        coordinator.api.get_device_control_value.side_effect = read
        with patch.object(entity, "async_write_ha_state"):
            unsubscribe = coordinator.async_add_listener(
                entity._handle_coordinator_update
            )
            try:
                assert await _entities(coordinator, kind, known) == []
                expected = time.fromisoformat(raw) if kind == "time" else raw
                assert entity.native_value == expected
                coordinator.ctrl_value_cache["TEST"][entity._field_id] = bad
                entity._handle_coordinator_update()
                assert entity.native_value == expected
                coordinator.ctrl_value_cache["TEST"][entity._field_id] = "null"
                entity._handle_coordinator_update()
                assert entity.native_value == expected
            finally:
                unsubscribe()
    finally:
        await coordinator.async_shutdown()


async def test_fresh_external_cloud_values_update_controls(hass):
    coordinator = _coordinator(hass)
    entity = (await _entities(coordinator))[0]
    try:
        cloud = coordinator._cached_cloud_data["TEST"]["data"]
        cloud[0]["val"] = "second"
        cloud[1]["val"] = "06:45"
        with patch.object(entity, "async_write_ha_state"):
            coordinator._sync_control_values_from_cloud("TEST")
            entity._handle_coordinator_update()
            assert entity.native_value == time(6, 45)
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,raw", [("time", "06:45"), ("text", "2028-02-29 12:34:56")]
)
async def test_telemetry_recovers_temporal_entities_after_retry_budget(hass, kind, raw):
    coordinator = _coordinator(hass, values=False)
    known = set()
    entity = (await _entities(coordinator, kind, known))[0]
    try:
        for _ in range(MAX_CONTROL_VALUE_RETRIES + 1):
            coordinator.cloud_revision += 1
            await _entities(coordinator, kind, known)
        reads = coordinator.api.get_device_control_value.await_count
        assert reads == len(FIELDS) * MAX_CONTROL_VALUE_RETRIES
        assert entity.native_value is None
        cloud = coordinator._cached_cloud_data["TEST"]["data"]
        cloud[0]["val"] = "recovered"
        cloud.append({"title": entity._api_name, "val": raw})
        coordinator.cloud_revision += 1
        with patch.object(entity, "async_write_ha_state"):
            remove_listener = coordinator.async_add_listener(
                entity._handle_coordinator_update
            )
            try:
                assert await _entities(coordinator, kind, known) == []
            finally:
                remove_listener()
        assert entity.native_value == (time(6, 45) if kind == "time" else raw)
        assert coordinator.api.get_device_control_value.await_count == reads
        coordinator.api.set_device_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_replaced_numbers_are_disabled_without_deleting_registry(hass):
    coordinator = _coordinator(hass)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    other_entry = MockConfigEntry(domain=DOMAIN)
    other_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entities = [*await _entities(coordinator), *await _entities(coordinator, "text")]
    try:
        originals = [
            registry.async_get_or_create(
                "number",
                DOMAIN,
                entity.legacy_number_unique_ids[0],
                config_entry=other_entry if index == 0 else entry,
                disabled_by=er.RegistryEntryDisabler.USER if index == 1 else None,
                original_name=f"Original name {index}",
            )
            for index, entity in enumerate(entities)
        ]
        originals = [
            registry.async_update_entity(
                old.entity_id, name=f"User custom name {index}"
            )
            for index, old in enumerate(originals)
        ]
        assert entities[-1].legacy_number_unique_ids == (
            "TEST__inverter_date",
            "TEST_inverter_date",
        )
        disable_replaced_numbers(hass, entry, entities)
        for index, old in enumerate(originals):
            preserved = registry.async_get(old.entity_id)
            assert preserved is not None and preserved.name == old.name
            expected = (
                None
                if index == 0
                else (
                    er.RegistryEntryDisabler.USER
                    if index == 1
                    else er.RegistryEntryDisabler.INTEGRATION
                )
            )
            assert preserved.disabled_by == expected
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,expected", [("time", "15:00:00"), ("text", "2026-10-13 13:36:16")]
)
async def test_native_values_are_published_through_home_assistant(hass, kind, expected):
    coordinator = _coordinator(hass)
    entity = (await _entities(coordinator, kind))[0]
    component = EntityComponent(logging.getLogger(__name__), kind, hass)
    await component.async_setup({})
    try:
        await component.async_add_entities([entity])
        state = hass.states.get(entity.entity_id)
        assert state is not None and state.state == expected
        assert state.attributes["control_transport"] == "cloud"
    finally:
        await component._async_reset()
        await coordinator.async_shutdown()
