"""Nameplate ratings and declared settings on devcode 2452, from #53.

This collector returns the inverter's nameplate ratings and its own setpoints
in the same call as the live readings. The ratings are facts about the hardware
and become diagnostic sensors; the setpoints are settings, five of them the
values of controls the account already publishes, and a profile declares those
so the support report stops counting them as readings that reach no entity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    is_setting_reading,
)
from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.device_support.device_registry import (
    temporal_control_kind,
)
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key
from custom_components.dessmonitor.text import DessMonitorClock
from custom_components.dessmonitor.time import DessMonitorTime

DEVCODE = 2452


def _resolved_key(title: str) -> str | None:
    """Return the sensor key a raw title reaches through this devcode."""
    mapped = apply_devcode_transformations(DEVCODE, {"title": title, "val": "1"})
    return resolve_sensor_key(mapped.get("title"), title)


@pytest.mark.parametrize(
    "title,expected_key",
    [
        ("AC output rating active power", "rated power"),
        ("AC output rating apparent power", "rated apparent power"),
        ("AC Output Rating Current", "rated current"),
        ("AC rated frequency", "rated frequency"),
        ("Battery Rating Voltage", "battery rated voltage"),
        ("Grid Rating Current", "grid rated current"),
    ],
)
def test_nameplate_ratings_reach_a_diagnostic_sensor(
    title: str, expected_key: str
) -> None:
    key = _resolved_key(title)

    assert key == expected_key
    assert SENSOR_TYPES[key]["entity_category"] == "diagnostic"


@pytest.mark.parametrize(
    "title",
    [
        # The five that are also controls on this account.
        "AC Output Rating Voltage",
        "Back To Discharge Voltage",
        "Battery bulk voltage",
        "Battery float voltage",
        # And the setpoints its control template does not advertise.
        "Battery recharge voltage",
        "Battery under voltage",
        "Low DC cut off voltage on second output",
    ],
)
def test_setpoints_are_declared_settings_rather_than_sensors(title: str) -> None:
    """A setting must not become a second entity for the same value."""
    assert is_setting_reading(DEVCODE, title) is True
    assert _resolved_key(title) is None


def test_a_declared_setting_matches_the_way_titles_are_compared() -> None:
    """Whitespace and case must not decide whether a setting is recognised."""
    assert is_setting_reading(DEVCODE, "  battery  bulk   voltage ") is True
    assert is_setting_reading(DEVCODE, "Battery Voltage") is False


# ---------------------------------------------------------------------------
# The clock and schedule fields, which a number entity cannot hold (#53).
# ---------------------------------------------------------------------------

_EVIDENCE = (
    Path(__file__).resolve().parent.parent / "docs/evidence/devcodes/analysis_2452.json"
)


def _evidence_controls() -> dict[str, str]:
    """Return the account's own control readback, field id to value."""
    payload = json.loads(_EVIDENCE.read_text("utf-8"))
    (device,) = payload["data"]["devices"]
    return {field["id"]: field["value"] for field in device["control_fields"]}


@pytest.mark.parametrize(
    "field_id,kind",
    [
        ("cts_start_time_for_enable_ac_charger_working", "time"),
        # The vendor's own spelling of "ending".
        ("cts_endin_time_for_enable_ac_charger_working", "time"),
        ("cts_scheduled_time_for_ac_output_on", "time"),
        ("cts_scheduled_time_for_ac_output_off", "time"),
        ("cts_set_date_time", "text"),
        # An ordinary numeric setting stays a number entity.
        ("bat_charging_current", None),
    ],
)
def test_the_clock_fields_leave_the_number_platform(
    field_id: str, kind: str | None
) -> None:
    """A number entity shows nothing for "00:00" or for a calendar string.

    The reporter in #53 saw these four controls, and the clock, sitting empty.
    """
    assert temporal_control_kind(DEVCODE, field_id) == kind
    assert temporal_control_kind(str(DEVCODE), field_id) == kind


@pytest.mark.parametrize(
    "field_id,kind",
    [
        ("cts_start_time_for_enable_ac_charger_working", "time"),
        ("cts_endin_time_for_enable_ac_charger_working", "time"),
        ("cts_scheduled_time_for_ac_output_on", "time"),
        ("cts_scheduled_time_for_ac_output_off", "time"),
        ("cts_set_date_time", "text"),
    ],
)
def test_each_declared_field_parses_the_value_the_account_returned(
    field_id: str, kind: str
) -> None:
    """The declaration is the API's readback, not an inference from the name.

    Each field has to exist on the account in the committed download and its
    value has to parse as the kind declared for it, because a kind that cannot
    read the value leaves the control as empty as the number entity was.
    """
    controls = _evidence_controls()
    assert field_id in controls, field_id
    raw = controls[field_id]

    entity = DessMonitorTime if kind == "time" else DessMonitorClock
    assert entity._parse_value(entity, raw) is not None, raw


def test_the_ids_do_not_reach_another_devcode() -> None:
    """Field ids repeat across devcodes with different meanings."""
    for field_id in _evidence_controls():
        assert temporal_control_kind(6544, field_id) is None
        assert temporal_control_kind(2449, field_id) is None
