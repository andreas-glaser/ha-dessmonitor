"""What a device publishes, keyed by sensor rather than by name (#63, item 4).

The download recorded which readings reach a sensor and nothing about the
entities themselves, and two defects cost weeks for want of it: in #53 the
reporter was asked twice for an entity id from Developer tools, because a
renamed entity and a recorder problem cannot be told apart from here, and in
#58 a device published two entities under one name and the one the summary fed
read 0 kWh until an owner happened to notice.

The decision this section was waiting on was how much of someone's system it
should publish, and the answer is: the sensor, never the name. An entity id
and a friendly name both carry whatever the owner called the thing, and these
files are attached to public issues.
"""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor import _entity_inventory
from custom_components.dessmonitor.const import DOMAIN

SERIAL = "SN-0001-REPORTER"


async def _registry_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    return entry


async def test_a_device_with_no_entities_yet_contributes_no_section(hass) -> None:
    entry = await _registry_entry(hass)

    assert _entity_inventory(hass, entry, SERIAL) is None


async def test_each_sensor_is_named_by_its_key_and_never_by_its_entity_id(
    hass,
) -> None:
    entry = await _registry_entry(hass)
    registry = er.async_get(hass)
    created = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{SERIAL}_battery_voltage",
        config_entry=entry,
        original_name="Roof Battery Voltage",
        suggested_object_id="my_shed_battery_volts",
    )
    hass.states.async_set(created.entity_id, "53.1")

    inventory = _entity_inventory(hass, entry, SERIAL)

    assert list(inventory["by_sensor"]) == ["Battery Voltage"]
    record = inventory["by_sensor"]["Battery Voltage"]
    assert record == {
        "platform": "sensor",
        "entities": 1,
        "disabled": 0,
        "name_customised": False,
        "states": ["ok"],
    }
    # The owner's own object id is nowhere in it.
    assert "my_shed_battery_volts" not in str(inventory)


async def test_an_unavailable_sensor_says_so(hass) -> None:
    """The reading reaches a sensor and the sensor still shows nothing.

    That is the shape of #81 - a vendor's word for a state offered to float()
    and discarded - and the file could not previously show it at all.
    """
    entry = await _registry_entry(hass)
    registry = er.async_get(hass)
    created = registry.async_get_or_create(
        "sensor", DOMAIN, f"{SERIAL}_battery_status", config_entry=entry
    )
    hass.states.async_set(created.entity_id, "unknown")

    inventory = _entity_inventory(hass, entry, SERIAL)

    assert inventory["by_sensor"]["Battery Status"]["states"] == ["unknown"]


async def test_a_disabled_entity_is_counted_and_not_queried(hass) -> None:
    entry = await _registry_entry(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{SERIAL}_shutdown_command",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    inventory = _entity_inventory(hass, entry, SERIAL)

    record = inventory["by_sensor"]["shutdown_command"]
    assert record["entities"] == 1
    assert record["disabled"] == 1
    assert record["states"] == []


async def test_two_sensors_under_one_name_are_named(hass) -> None:
    """The #58 defect itself, in the file rather than in an owner's eye.

    ``energyToday`` and ``Energy Today`` are separate keys that publish one
    display name, and the one the plant summary feeds reads 0 kWh wherever the
    vendor leaves that field unset.
    """
    entry = await _registry_entry(hass)
    registry = er.async_get(hass)
    for unique_id in (f"{SERIAL}_energytoday", f"{SERIAL}_energy_today"):
        created = registry.async_get_or_create(
            "sensor",
            DOMAIN,
            unique_id,
            config_entry=entry,
            original_name="Energy Today",
        )
        hass.states.async_set(created.entity_id, "0.0")

    inventory = _entity_inventory(hass, entry, SERIAL)

    assert inventory["names_published_by_more_than_one_sensor"] == {
        "Energy Today": ["Energy Today", "energyToday"]
    }


async def test_a_customised_entity_says_so_without_saying_what(hass) -> None:
    """An owner who renamed one, said without saying what they called it."""
    entry = await _registry_entry(hass)
    registry = er.async_get(hass)
    created = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{SERIAL}_data_source",
        config_entry=entry,
        original_name="Roof Data Source",
    )
    registry.async_update_entity(created.entity_id, name="Shed telemetry source")
    hass.states.async_set(created.entity_id, "Local")

    inventory = _entity_inventory(hass, entry, SERIAL)

    assert inventory["by_sensor"]["Data Source"]["name_customised"] is True
    assert "Shed telemetry source" not in str(inventory)


async def test_another_devices_entities_are_not_counted(hass) -> None:
    """One serial's inventory, on an account with several inverters."""
    entry = await _registry_entry(hass)
    registry = er.async_get(hass)
    for serial in (SERIAL, "SN-0002-REPORTER"):
        registry.async_get_or_create(
            "sensor", DOMAIN, f"{serial}_battery_voltage", config_entry=entry
        )

    inventory = _entity_inventory(hass, entry, SERIAL)

    assert inventory["by_sensor"]["Battery Voltage"]["entities"] == 1


async def test_the_section_reaches_the_entry_download(hass) -> None:
    """End to end, through the builder the entry button calls."""
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.dessmonitor import _build_device_support_report

    entry = await _registry_entry(hass)
    registry = er.async_get(hass)
    created = registry.async_get_or_create(
        "sensor", DOMAIN, f"{SERIAL}_grid_frequency", config_entry=entry
    )
    hass.states.async_set(created.entity_id, "49.97")

    coordinator = MagicMock()
    coordinator.api.get_device_control_fields = AsyncMock(return_value={})
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    payload = {
        "collector": {"pn": "Q0000PN0001"},
        "device": {"devcode": 6515, "devaddr": 1, "alias": "Roof"},
        "data": [{"title": "Grid Frequency", "val": "49.97", "unit": "Hz"}],
    }

    report = await _build_device_support_report(
        hass, coordinator, entry, SERIAL, payload
    )

    assert report["entity_inventory"]["by_sensor"]["Grid Frequency"]["states"] == [
        "ok"
    ]
    assert report["checksum"]
