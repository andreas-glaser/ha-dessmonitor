"""Sensor platform setup behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.sensor import async_setup_entry


async def test_dynamic_sensor_add_does_not_request_cloud_refresh() -> None:
    """Adding entities must respect the configured API polling interval."""
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-SERIAL": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"alias": "Test inverter", "devcode": 2376, "devaddr": 1},
            "data": [{"title": "Grid Voltage", "val": 230, "unit": "V"}],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    entry = MagicMock(entry_id="entry")
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    assert len(async_add_entities.call_args.args) == 1
    assert len(async_add_entities.call_args.args[0]) == 1


@pytest.mark.parametrize(
    ("devcode", "title"),
    [(518, "apparent power value"), (6416, "Output Apparent Power")],
)
@pytest.mark.parametrize(
    ("unit", "value", "expected"),
    [
        ("kVA", "0.360", 360),
        ("kVA", "0", 0),
        ("VA", "360", 360),
        ("", "360", 360),
        (None, "360", 360),
        ("kVA", "--", None),
        ("kVA", "invalid", None),
        ("kVA", None, None),
    ],
)
async def test_apparent_power_uses_each_readings_unit(
    devcode: int,
    title: str,
    unit: str | None,
    value: str | None,
    expected: int | None,
) -> None:
    """Publish VA consistently even when cloud/local updates change units."""
    point = {"title": title, "val": value, "unit": unit}
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-SERIAL": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"devcode": devcode, "devaddr": 1},
            "data": [point],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()
    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
    (entity,) = added.call_args.args[0]

    assert entity.unique_id == "TEST-SERIAL_output_apparent_power"
    assert entity.native_unit_of_measurement == "VA"
    assert entity.device_class == "apparent_power"
    assert entity.state_class == "measurement"
    assert entity.native_value == expected
    assert point == {"title": title, "val": value, "unit": unit}

    for updated_unit, updated_value in [("VA", "450"), ("kVA", "0.450")]:
        coordinator.data["TEST-SERIAL"]["data"] = [
            {"title": title, "val": updated_value, "unit": updated_unit}
        ]
        assert entity.native_value == 450
        assert entity.native_unit_of_measurement == "VA"


@pytest.mark.parametrize(
    ("title", "value"),
    [
        ("Data Source", "Local"),
        ("Operating mode", "Battery"),
        ("Inverter Status", "Normal"),
    ],
)
async def test_a_text_sensor_publishes_no_unit_at_all(title: str, value: str) -> None:
    """An empty unit is not the same as no unit (#53).

    Home Assistant decides a sensor is a continuous measurement by testing
    whether the unit_of_measurement attribute is *present*, not whether it
    holds anything. Publishing "" therefore kept every text and enum sensor
    out of the logbook, and out of the query behind the historical view, so
    the reporter's Data Source had no Activity at all and drew an empty
    numeric chart where a state timeline belongs.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-SERIAL": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": title, "val": value, "unit": ""}],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()

    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
    (entity,) = added.call_args.args[0]

    assert entity.native_unit_of_measurement is None
    assert "unit_of_measurement" not in (entity.capability_attributes or {})
    assert entity.state_class is None


async def test_power_factor_stays_continuous_without_a_unit() -> None:
    """The one unitless reading that is a measurement says so another way.

    Power Factor carries no unit either, and it must keep being treated as
    continuous or every refresh would add a logbook entry for it. Its state
    class is what does that, so dropping the empty unit is safe for it.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-SERIAL": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"devcode": 684, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": "power factor", "val": "1.000", "unit": ""}],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()

    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
    (entity,) = added.call_args.args[0]

    assert entity.native_unit_of_measurement is None
    assert entity.state_class == "measurement"


@pytest.mark.parametrize(
    ("first", "second", "unique_id"),
    [
        # Each pair is two keys carrying one display name on purpose, one per
        # vendor spelling. The id is the one the first of the two publishes.
        ("SOC", "State of Charge", "TEST-SERIAL_soc"),
        ("Batt Current", "Battery Current", "TEST-SERIAL_batt_current"),
        ("batt power", "Battery Power", "TEST-SERIAL_batt_power"),
        ("work state", "Operating mode", "TEST-SERIAL_work_state"),
        ("energyToday", "Energy Today", "TEST-SERIAL_energytoday"),
        ("energyTotal", "Energy Total", "TEST-SERIAL_energytotal"),
    ],
)
async def test_a_device_gets_one_entity_per_name(
    first: str, second: str, unique_id: str
) -> None:
    """Two keys with one name must not become two entities on one device.

    The alias pairs exist so either vendor spelling reaches a sensor. A
    collector that reports both resolves them to different keys, so the
    per-key check lets both through and the owner sees two entities with the
    same name, the second reading whatever the vendor left in its field. That
    is how an Energy Today sensor fed by an unset summary field read 0 kWh
    beside a working one (#58); only the summary merge guarded against it, and
    only for the pair that comes through the summary endpoint.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-SERIAL": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"devcode": 6514, "devaddr": 1},
            "data": [
                {"title": first, "val": "11", "unit": ""},
                {"title": second, "val": "0", "unit": ""},
            ],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()

    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)

    # One entity, not two, and it is the one the first reading publishes:
    # on a real payload that is the measured one, because a merged summary
    # field is appended after it.
    (entity,) = added.call_args.args[0]
    assert entity.unique_id == unique_id
    assert entity.native_value in (11, 11.0, "11")


async def test_the_reading_a_summary_field_duplicates_is_the_one_kept() -> None:
    """The order matters, because one of the two is the broken one.

    A collector's own counter arrives in the telemetry and the summary
    endpoint's copy is appended to it, so keeping the first keeps the reading
    the inverter reported rather than the field the vendor may never set.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-SERIAL": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"devcode": 684, "devaddr": 1},
            "data": [
                {"title": "today energy", "val": "7.65", "unit": "kWh"},
                {"title": "energyToday", "val": "0.0000", "unit": "kWh"},
            ],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()

    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)

    (entity,) = added.call_args.args[0]
    assert entity.unique_id == "TEST-SERIAL_energy_today"
    assert entity.native_value == 7.65
