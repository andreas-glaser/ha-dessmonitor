"""Exercise durable migration through HA's real entity registry."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.device_support.device_registry import (
    map_control_field,
)
from custom_components.dessmonitor.number import (
    DessMonitorNumber,
    _async_build_number_entities,
)
from custom_components.dessmonitor.temporal_controls import disable_replaced_numbers

from .test_temporal_controls import FIELDS, _coordinator, _entities


async def test_migration_looks_up_actual_number_ids_without_normalizing_them(hass):
    coordinator = _coordinator(hass)
    try:
        replacements = [
            *await _entities(coordinator),
            *await _entities(coordinator, "text"),
        ]
        actual_ids = []
        for name, (field_id, raw) in FIELDS.items():
            number = DessMonitorNumber(
                coordinator,
                "TEST",
                {"devcode": 6544},
                {"pn": "PN"},
                map_control_field(6544, name),
                name,
                field_id,
                raw,
                None,
                None,
            )
            actual_ids.append(number.unique_id)
        for entity, unique_id in zip(replacements, actual_ids, strict=True):
            assert unique_id in entity.legacy_number_unique_ids
        assert all(
            len(entity.legacy_number_unique_ids) == 1 for entity in replacements[:-1]
        )
        assert actual_ids == [
            "TEST_secondary_charging_priority_start_time",
            "TEST_secondary_charging_priority_end_time",
            "TEST_secondary_output_priority_start_time",
            "TEST_secondary_output_priority_end_time",
            "TEST_inverter_date",
        ]
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,legacy_id",
    [
        ("time", "TEST_secondary_charging_priority_start_time"),
        ("text", "TEST__inverter_date"),
        ("text", "TEST_inverter_date"),
    ],
)
@pytest.mark.parametrize(
    "disabled_by",
    [None, er.RegistryEntryDisabler.USER, er.RegistryEntryDisabler.INTEGRATION],
)
async def test_user_reenable_survives_registry_reload_and_fresh_discovery(
    hass, hass_storage, disabled_by, kind, legacy_id
):
    coordinator = _coordinator(hass)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    # The preloaded test registry uses StoreWithoutWriteLoad. Construct a real
    # registry store backed by hass_storage to exercise persistence and reload.
    registry = er.EntityRegistry(hass)
    await registry.async_load()
    entity = (await _entities(coordinator, kind))[0]
    old = registry.async_get_or_create(
        "number",
        DOMAIN,
        legacy_id,
        config_entry=entry,
        disabled_by=disabled_by,
    )
    registry.async_update_entity_options(old.entity_id, DOMAIN, {"unrelated": "keep"})
    registry.async_update_entity_options(
        old.entity_id, "number", {"display_precision": 1}
    )
    try:
        with patch(
            "custom_components.dessmonitor.temporal_controls.er.async_get",
            return_value=registry,
        ):
            disable_replaced_numbers(hass, entry, [entity])
        migrated = registry.async_get(old.entity_id)
        assert migrated.disabled_by == (
            disabled_by or er.RegistryEntryDisabler.INTEGRATION
        )
        # Simulate a deliberate user choice after migration, including a rename.
        renamed = registry.async_update_entity(
            old.entity_id, new_entity_id="number.user_kept_schedule", disabled_by=None
        )
        await registry._store.async_save(registry._data_to_save())
        assert er.STORAGE_KEY in hass_storage
        reloaded = er.EntityRegistry(hass)
        await reloaded.async_load()
        # A fresh discovery set removes the in-memory known-set protection.
        replacements = await _entities(coordinator, kind, known=set())
        with patch(
            "custom_components.dessmonitor.temporal_controls.er.async_get",
            return_value=reloaded,
        ):
            disable_replaced_numbers(hass, entry, replacements)
        preserved = reloaded.async_get(renamed.entity_id)
        assert preserved.id == old.id
        assert preserved.disabled_by is None
        assert preserved.options[DOMAIN]["unrelated"] == "keep"
        assert preserved.options["number"]["display_precision"] == 1
        assert preserved.options[DOMAIN]["temporal_number_migrated"] is True
        coordinator.api.set_device_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,legacy_id",
    [
        ("time", "TEST_secondary_charging_priority_start_time"),
        ("text", "TEST__inverter_date"),
        ("text", "TEST_inverter_date"),
    ],
)
async def test_missing_or_other_entry_number_does_not_mark_migration_done(
    hass, kind, legacy_id
):
    coordinator = _coordinator(hass)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN)
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    entity = (await _entities(coordinator, kind))[0]
    try:
        # Discovery without a legacy number must not consume a later migration.
        disable_replaced_numbers(hass, entry, [entity])
        wrong_entry = registry.async_get_or_create(
            "number", DOMAIN, legacy_id, config_entry=other
        )
        disable_replaced_numbers(hass, entry, [entity])
        assert registry.async_get(wrong_entry.entity_id).disabled_by is None
        assert DOMAIN not in registry.async_get(wrong_entry.entity_id).options
        registry.async_remove(wrong_entry.entity_id)
        matching = registry.async_get_or_create(
            "number", DOMAIN, legacy_id, config_entry=entry
        )
        disable_replaced_numbers(hass, entry, [entity])
        assert (
            registry.async_get(matching.entity_id).disabled_by
            == er.RegistryEntryDisabler.INTEGRATION
        )
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "legacy_ids",
    [
        ("TEST__inverter_date",),
        ("TEST_inverter_date",),
        ("TEST__inverter_date", "TEST_inverter_date"),
    ],
)
async def test_clock_retires_each_historical_number_without_renaming(hass, legacy_ids):
    """Both upgrade paths and a registry containing both histories are supported."""
    coordinator = _coordinator(hass)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    originals = [
        registry.async_get_or_create("number", DOMAIN, uid, config_entry=entry)
        for uid in legacy_ids
    ]
    try:
        clocks = await _entities(coordinator, "text")
        assert len(clocks) == 1
        assert clocks[0].unique_id == "TEST_sys_eybond_read_44023"
        assert (
            await _entities(coordinator, "text", {"TEST:sys_eybond_read_44023"}) == []
        )
        assert await _async_build_number_entities(coordinator, set()) == []
        disable_replaced_numbers(hass, entry, clocks)
        for old in originals:
            preserved = registry.async_get(old.entity_id)
            assert preserved.id == old.id
            assert preserved.unique_id == old.unique_id
            assert preserved.disabled_by == er.RegistryEntryDisabler.INTEGRATION
            assert preserved.options[DOMAIN]["temporal_number_migrated"] is True
        coordinator.api.set_device_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_later_clock_alias_migrates_without_overriding_reenabled_old_id(hass):
    """A per-record marker must not skip the second historical ID or re-disable the first."""
    coordinator = _coordinator(hass)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "number", DOMAIN, "TEST__inverter_date", config_entry=entry
    )
    try:
        disable_replaced_numbers(hass, entry, await _entities(coordinator, "text"))
        registry.async_update_entity(old.entity_id, disabled_by=None)
        newer = registry.async_get_or_create(
            "number", DOMAIN, "TEST_inverter_date", config_entry=entry
        )
        disable_replaced_numbers(hass, entry, await _entities(coordinator, "text"))
        assert registry.async_get(old.entity_id).disabled_by is None
        assert (
            registry.async_get(newer.entity_id).disabled_by
            == er.RegistryEntryDisabler.INTEGRATION
        )
        assert (
            registry.async_get(newer.entity_id).options[DOMAIN][
                "temporal_number_migrated"
            ]
            is True
        )
        coordinator.api.set_device_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()
