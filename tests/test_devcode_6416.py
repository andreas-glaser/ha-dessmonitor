"""PowMr telemetry and priority values from the analysis attached to issue #36."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.api import DessMonitorAPI
from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.device_support.device_registry import (
    apply_devcode_transformations,
    is_devcode_supported,
    needs_parameter_fetch,
)
from custom_components.dessmonitor.sensor import async_setup_entry

FIXTURE = Path(__file__).parent / "fixtures/devcode_6416_query_device_last_data.json"


def test_device_is_supported_without_extra_parameter_fetch_or_warning(caplog):
    assert is_devcode_supported(6416)
    assert not needs_parameter_fetch(6416)
    point = {"title": "Battery Capacity", "val": "72", "unit": "%"}
    with caplog.at_level(logging.WARNING):
        result = apply_devcode_transformations(6416, point)
    assert result == {"title": "State of Charge", "val": "72", "unit": "%"}
    assert point["title"] == "Battery Capacity"
    assert not caplog.records


@pytest.mark.parametrize("pv2_power", ["0", "350"])
async def test_reported_telemetry_through_api_and_sensor_platform(
    cloud_transport, pv2_power
):
    payload = json.loads(FIXTURE.read_text())
    for point in payload["dat"]:
        if point["title"] == "PV2 input power":
            point["val"] = pv2_power
    session, connector = cloud_transport
    connector.payload = payload
    api = DessMonitorAPI("test-user", "test-password", session=session)
    api.token, api.secret = "test-token", "test-secret"
    points = await api.get_device_last_data("TEST-COLLECTOR", 6416, 5, "TEST-INVERTER")
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-INVERTER": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"devcode": 6416, "devaddr": 5},
            "data": points,
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()
    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
    entities = {entity.unique_id: entity for entity in added.call_args.args[0]}
    expected = {
        "pv2_voltage": (0, "V"),
        "pv2_charger_power": (float(pv2_power), "W"),
        "operating_mode": ("Battery", ""),
        "grid_voltage": (237.1, "V"),
        "grid_frequency": (49.9, "Hz"),
        "pv1_voltage": (315.5, "V"),
        "pv1_charger_power": (787, "W"),
        "pv_total_charger_power": (787, "W"),
        "battery_voltage": (53.4, "V"),
        "state_of_charge": (72, "%"),
        "battery_charging_current": (0, "A"),
        "battery_discharge_current": (1, "A"),
        "output_voltage": (230.2, "V"),
        "output_frequency": (49.9, "Hz"),
        "output_apparent_power": (874, "VA"),
        "output_active_power": (781, "W"),
        "load_percent": (14, "%"),
        "output_priority": ("Solar - Battery - Utility", ""),
        "charger_source_priority": ("Solar and Utility", ""),
    }
    assert set(entities) == {f"TEST-INVERTER_{suffix}" for suffix in expected}
    for suffix, (value, unit) in expected.items():
        entity = entities[f"TEST-INVERTER_{suffix}"]
        assert entity.native_value == value, suffix
        assert entity.native_unit_of_measurement == unit, suffix
        if entity.options is not None:
            assert entity.native_value in entity.options


@pytest.mark.parametrize(
    ("title", "raw", "expected"),
    [
        ("Output Source Priority", "Utility", "Utility First"),
        ("Output Source Priority", "Solar", "Solar First"),
        ("Output Source Priority", "SBU", "Solar - Battery - Utility"),
        ("Charger Source Priority", "Solar priority", "Solar First"),
        ("Charger Source Priority", "Solar and mains", "Solar and Utility"),
        ("Charger Source Priority", "Solar only", "Only Solar"),
        ("Working State", "Invert Mode", "Battery"),
        ("Working State", "Future mode", "Future mode"),
    ],
)
def test_observed_modes_and_documented_priority_options(title, raw, expected):
    result = apply_devcode_transformations(6416, {"title": title, "val": raw})
    assert result["val"] == expected
