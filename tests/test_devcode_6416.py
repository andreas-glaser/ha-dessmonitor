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
        "operating_mode": ("Battery", None),
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
        "output_priority": ("Solar - Battery - Utility", None),
        "charger_source_priority": ("Solar and Utility", None),
    }
    assert set(entities) == {f"TEST-INVERTER_{suffix}" for suffix in expected}
    # The enum sensors expect None rather than "": Home Assistant tests for
    # the presence of the unit attribute, so an empty one kept them out of the
    # logbook and out of the historical view entirely (#53).
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


# The titles the iSolar SMH-III 6.2 kW download reported as reaching no entity
# (#81), which are the ones devcodes 2477 and 2341 already name. The four this
# family leaves unmapped identify the hardware and carry no unit, so none of
# them holds a Repairs card open.
REPORTED_UNMAPPED = [
    "AC Input Range",
    "Auto Return To Default Display Screen",
    "Battery Equalization",
    "Battery Equalization Activated Immediately",
    "Battery Equalization Interval",
    "Battery Equalization Voltage",
    "Battery Equalized Time",
    "Battery Equalized Timeout",
    "Battery Type",
    "Beeps While Primary Source Interupt",
    "Bulk Charging Voltage",
    "Buzzer Alarm",
    "Comeback Battery Mode Voltage Point Under (SBU Priority)",
    "Comeback Utility Mode Voltage Point Under (SBU Priority)",
    "Floating Charging Voltage",
    "LCD Backlight",
    "Low Battery Cut-off Voltage",
    "Mains Status",
    "Max Total Charge Current",
    "Max Utility Charge Current",
    "Nominal AC Current",
    "Nominal AC Voltage",
    "Nominal Output Current",
    "Nominal Output Frequency",
    "Nominal Output Voltage",
    "Nonimal Output Active Power",
    "Nonimal Output Apparent Power",
    "Over Temperature Auto Restart",
    "Overload Auto Restart",
    "Power Saving Mode",
    "Rated Battery Voltage",
    "Record Fault Code",
    "Transfer To Bypass @ Overload",
]

IDENTITY_TITLES = {
    "Battery Piece",
    "Machine Type",
    "Main CPU Version",
    "Secondary CPU Version",
}


def _resolved_key(title: str) -> str | None:
    from custom_components.dessmonitor.support_report import resolved_key_for

    return resolved_key_for(6416, {"title": title, "val": "1"})


def test_every_reported_title_is_accounted_for() -> None:
    """Each one reaches a sensor, is a declared setting, or names the hardware."""
    from custom_components.dessmonitor.device_support import is_setting_reading

    unaccounted = [
        title
        for title in REPORTED_UNMAPPED
        if _resolved_key(title) is None
        and not is_setting_reading(6416, title)
        and title not in IDENTITY_TITLES
    ]

    assert unaccounted == []


def test_the_two_pv_strings_stay_this_devcode_s_own() -> None:
    """The family is single-string; this collector reports PV1, PV2 and a total."""
    assert _resolved_key("PV1 Input Voltage") == "PV1 Voltage"
    assert _resolved_key("PV1 Input Power") == "PV1 Charger Power"
    assert _resolved_key("PV2 input voltage") == "PV2 Voltage"
    assert _resolved_key("PV2 input power") == "PV2 Charger Power"
    assert _resolved_key("PV total Power") == "PV Total Charger Power"


def test_the_nameplate_ratings_become_their_own_sensors() -> None:
    """A rating is a fact about the hardware, not a setting (#53)."""
    assert _resolved_key("Nominal AC Voltage") == "grid rated voltage"
    assert _resolved_key("Nominal AC Current") == "grid rated current"
    assert _resolved_key("Nominal Output Voltage") == "rated voltage"
    assert _resolved_key("Nominal Output Current") == "rated current"
    assert _resolved_key("Nominal Output Frequency") == "rated frequency"
    assert _resolved_key("Nonimal Output Active Power") == "rated power"
    assert _resolved_key("Nonimal Output Apparent Power") == "rated apparent power"
    assert _resolved_key("Rated Battery Voltage") == "battery rated voltage"
    assert _resolved_key("Mains Status") == "Grid Status"


def test_the_setpoints_are_settings_not_missing_readings() -> None:
    """The reporter's 37 unmapped readings are mostly the inverter's setpoints."""
    from custom_components.dessmonitor.device_support import is_setting_reading

    for title in (
        "Bulk Charging Voltage",
        "Floating Charging Voltage",
        "Low Battery Cut-off Voltage",
        "Max Total Charge Current",
        "Max Utility Charge Current",
        "Comeback Battery Mode Voltage Point Under (SBU Priority)",
        "Comeback Utility Mode Voltage Point Under (SBU Priority)",
        "Battery Type",
        "AC Input Range",
        # Spelled one way as a reading and another as a control.
        "Beeps While Primary Source Interupt",
        "Transfer To Bypass @ Overload",
        "Auto Return To Default Display Screen",
    ):
        assert is_setting_reading(6416, title), title


def test_the_option_lists_are_left_as_the_collector_sends_them() -> None:
    """Narrowing them to the battery class would move an existing select (#40)."""
    from custom_components.dessmonitor.device_support.device_registry import (
        filter_control_options,
    )

    options = {"25.0": "25.0V", "61.0": "61.0V"}

    assert (
        filter_control_options(
            6416,
            "bat_sp_bulk_charging_voltage",
            options,
            [{"title": "Rated Battery Voltage", "val": "48.0"}],
        )
        == options
    )
