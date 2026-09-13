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
