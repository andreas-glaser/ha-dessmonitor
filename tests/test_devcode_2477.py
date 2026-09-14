"""Telemetry and mixed battery-voltage options reported in issue #40."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dessmonitor.api import DessMonitorAPI
from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.device_support.device_registry import (
    apply_devcode_transformations,
    is_devcode_supported,
    needs_parameter_fetch,
)
from custom_components.dessmonitor.select import _async_build_select_entities
from custom_components.dessmonitor.sensor import async_setup_entry

FIXTURE = Path(__file__).parent / "fixtures/devcode_2477_query_device_last_data.json"

# Endpoints of the separate voltage option groups in the contributor's report.
VOLTAGE_CONTROLS = [
    (
        "bat_sp_battery_equalization_voltage",
        "Battery Equalization Voltage",
        ["25.0V", "31.5V"],
        ["48.0V", "61.0V"],
    ),
    (
        "bat_sp_bulk_charging_voltage",
        "Bulk Charging Voltage",
        ["25.0V", "31.5V"],
        ["48.0V", "61.0V"],
    ),
    (
        "bat_sp_floting_charging_voltage",
        "Floating Charging Voltage",
        ["25.0V", "31.5V"],
        ["48.0V", "61.0V"],
    ),
    (
        "bat_sp_battery_mode_voltage",
        "Comeback battery mode voltage point (SBU priority)",
        ["24.0V", "29.0V"],
        ["48.0V", "58.0V"],
    ),
    (
        "bat_sp_utility_mode_voltage",
        "Comeback utility mode voltage point (SBU priority)",
        ["21.0V", "25.5V"],
        ["42.0V", "51.0V"],
    ),
    (
        "bat_sp_low_battery_voltage",
        "Low Battery Cut-off Voltage",
        ["20.0V", "24.0V"],
        ["40.0V", "48.0V"],
    ),
]


def _coordinator(
    data,
    name="Bulk Charging Voltage",
    param_id="bat_sp_bulk_charging_voltage",
    options=None,
    devcode=2477,
):
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        "TEST-INVERTER": {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"devcode": devcode, "devaddr": 1},
            "data": data,
        }
    }
    options = (
        options
        if options is not None
        else {"25.0": "25.0V", "48.0": "48.0V", "61.0": "61.0V"}
    )
    coordinator.async_get_controls_with_values = AsyncMock(
        return_value=(
            {name: {"type": "options", "id": param_id, "options": options}},
            {param_id: "48.0"},
        )
    )
    coordinator.ctrl_value_cache = {"TEST-INVERTER": {param_id: "48.0"}}
    coordinator.api.set_device_control_value = AsyncMock(return_value={"err": 0})
    return coordinator


def test_registration_and_observed_mode_without_extra_parameter_fetch(caplog):
    assert is_devcode_supported(2477)
    assert not needs_parameter_fetch(2477)
    with caplog.at_level(logging.WARNING):
        assert apply_devcode_transformations(
            2477, {"title": "Working State", "val": "Line Mode"}
        ) == {"title": "Operating mode", "val": "Line"}
    assert not caplog.records


async def test_reported_telemetry_through_api_and_sensor_platform(cloud_transport):
    session, connector = cloud_transport
    connector.payload = json.loads(FIXTURE.read_text())
    api = DessMonitorAPI("test-user", "test-password", session=session)
    api.token, api.secret = "test-token", "test-secret"
    points = await api.get_device_last_data("TEST-COLLECTOR", 2477, 1, "TEST-INVERTER")
    coordinator = _coordinator(points)
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()
    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
    entities = {entity.unique_id: entity for entity in added.call_args.args[0]}
    expected = {
        "operating_mode": ("Line", ""),
        "grid_voltage": (244.8, "V"),
        "grid_frequency": (49.9, "Hz"),
        "pv_voltage": (359.6, "V"),
        "pv_charge_power": (2534, "W"),
        "battery_voltage": (53.2, "V"),
        "state_of_charge": (100, "%"),
        "battery_charging_current": (0, "A"),
        "battery_discharge_current": (0, "A"),
        "output_voltage": (244.8, "V"),
        "output_frequency": (49.9, "Hz"),
        "output_apparent_power": (1564, "VA"),
        "output_active_power": (1556, "W"),
        "load_percent": (28, "%"),
    }
    assert set(entities) == {f"TEST-INVERTER_{suffix}" for suffix in expected}
    for suffix, (value, unit) in expected.items():
        entity = entities[f"TEST-INVERTER_{suffix}"]
        assert entity.native_value == value
        assert entity.native_unit_of_measurement == unit
        if entity.options is not None:
            assert entity.native_value in entity.options


@pytest.mark.parametrize(
    ("title", "value", "expected"),
    [
        ("Output Source Priority", "Utility", "Utility First"),
        ("Output Source Priority", "Solar", "Solar First"),
        ("Output Source Priority", "SBU", "Solar - Battery - Utility"),
        ("Charger Source Priority", "Solar priority", "Solar First"),
        ("Charger Source Priority", "Solar and mains", "Solar and Utility"),
        ("Charger Source Priority", "Solar only", "Only Solar"),
        ("Working State", "Future mode", "Future mode"),
    ],
)
def test_reported_priority_options_and_unknown_mode(title, value, expected):
    assert (
        apply_devcode_transformations(2477, {"title": title, "val": value})["val"]
        == expected
    )


@pytest.mark.parametrize(
    ("param_id", "name", "options24", "options48"), VOLTAGE_CONTROLS
)
@pytest.mark.parametrize("voltage", [24, 48])
async def test_voltage_options_match_rating_and_preserve_api_keys(
    param_id, name, options24, options48, voltage
):
    labels = ["12.0V", *options24, *options48]
    options = {str(index): label for index, label in enumerate(labels)}
    coordinator = _coordinator(
        [{"title": "Battery Piece", "val": f"{voltage}V(5KW)"}], name, param_id, options
    )
    entity = (await _async_build_select_entities(coordinator, set()))[0]
    expected = options24 if voltage == 24 else options48
    assert entity.options == expected
    assert entity.available
    assert (
        coordinator.async_get_controls_with_values.return_value[0][name]["options"]
        == options
    )
    rejected = options48 if voltage == 24 else options24
    with pytest.raises(ValueError, match="Invalid option"):
        await entity.async_select_option(rejected[0])
    coordinator.api.set_device_control_value.assert_not_awaited()
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_select_option(expected[-1])
        entity._handle_coordinator_update()
    coordinator.api.set_device_control_value.assert_awaited_once_with(
        pn="TEST-COLLECTOR",
        devcode=2477,
        devaddr=1,
        sn="TEST-INVERTER",
        param_id=param_id,
        value=next(key for key, label in options.items() if label == expected[-1]),
    )
    assert entity.current_option == expected[-1]


@pytest.mark.parametrize("rating", ["48", "48.0", "48V", " 48.0 V "])
async def test_rated_battery_voltage_is_accepted(rating):
    coordinator = _coordinator([{"title": "Rated Battery Voltage", "val": rating}])
    entity = (await _async_build_select_entities(coordinator, set()))[0]
    assert entity.options == ["48.0V", "61.0V"]
    assert entity.current_option == "48.0V"


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"title": "Battery Voltage", "val": "53.2"}],
        [{"title": "Rated Battery Voltage", "val": "nan"}],
        [{"title": "Battery Piece", "val": "12V(1KW)"}],
        [
            {"title": "Battery Piece", "val": "48V(5KW)"},
            {"title": "Rated Battery Voltage", "val": "24"},
        ],
    ],
)
async def test_unknown_or_conflicting_rating_blocks_voltage_writes(data, caplog):
    coordinator = _coordinator(data)
    with caplog.at_level(logging.WARNING):
        entity = (await _async_build_select_entities(coordinator, set()))[0]
        assert not entity.available
        assert entity.options == []
        with pytest.raises(ValueError):
            await entity.async_select_option("48.0V")
    coordinator.api.set_device_control_value.assert_not_awaited()
    assert len(caplog.records) == 1


async def test_options_recover_and_reject_stale_rating_before_write():
    coordinator = _coordinator([])
    entity = (await _async_build_select_entities(coordinator, set()))[0]
    unique_id = entity.unique_id
    with patch.object(entity, "async_write_ha_state"):
        coordinator.data["TEST-INVERTER"]["data"] = [
            {"title": "Battery Piece", "val": "48V(5KW)"}
        ]
        entity._handle_coordinator_update()
        assert entity.available
        assert entity.options == ["48.0V", "61.0V"]
        coordinator.data["TEST-INVERTER"]["data"] = [
            {"title": "Battery Piece", "val": "24V(3KW)"}
        ]
        with pytest.raises(ValueError, match="Invalid option"):
            await entity.async_select_option("48.0V")
    assert entity.unique_id == unique_id
    assert entity.options == ["25.0V"]
    assert entity.current_option is None
    coordinator.api.set_device_control_value.assert_not_awaited()


@pytest.mark.parametrize(
    "options",
    [
        {"25.0": "25.0V", "31.5": "31.5V"},
        {"48.0": "48.0V", "unknown": "unsupported"},
        {"48.0": "48.0V", "bad": "NaNV"},
    ],
)
async def test_unusable_voltage_options_block_writes(options):
    coordinator = _coordinator(
        [{"title": "Rated Battery Voltage", "val": "48"}], options=options
    )
    entity = (await _async_build_select_entities(coordinator, set()))[0]
    assert not entity.available
    with pytest.raises(ValueError, match="Invalid option"):
        await entity.async_select_option("48.0V")
    coordinator.api.set_device_control_value.assert_not_awaited()


async def test_rating_is_per_device_and_loss_of_metadata_disables_only_its_controls():
    first = _coordinator([{"title": "Battery Piece", "val": "48V(5KW)"}])
    second = _coordinator([{"title": "Rated Battery Voltage", "val": "24"}])
    first.data["OTHER-INVERTER"] = second.data["TEST-INVERTER"]
    entities = await _async_build_select_entities(first, set())
    entity48, entity24 = entities
    assert entity48.options == ["48.0V", "61.0V"]
    assert entity24.options == ["25.0V"]
    first.data["TEST-INVERTER"]["data"] = []
    with patch.object(entity48, "async_write_ha_state"):
        entity48._handle_coordinator_update()
    assert not entity48.available
    assert entity48.current_option is None
    assert entity24.available
    assert entity24.options == ["25.0V"]


@pytest.mark.parametrize(
    ("devcode", "param_id"),
    [(2477, "los_output_voltage"), (6416, "bat_sp_bulk_charging_voltage")],
)
async def test_other_controls_and_devcodes_keep_api_options(devcode, param_id):
    options = {"220": "220Vac", "230": "230Vac", "240": "240Vac"}
    coordinator = _coordinator([], param_id=param_id, options=options, devcode=devcode)
    entity = (await _async_build_select_entities(coordinator, set()))[0]
    assert entity.options == list(options.values())
    assert entity.available
