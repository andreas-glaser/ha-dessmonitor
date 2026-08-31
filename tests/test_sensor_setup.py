"""Sensor platform setup behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

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
