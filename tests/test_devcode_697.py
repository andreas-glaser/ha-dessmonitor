"""Devcode 697, a PV1800 MD PV18-5048 VHM on ShineMonitor (#79).

Eighteen of the twenty-one readings already resolved without a profile, so
what this devcode needed was three readings and a name, not a mapping table.
Every title and value below comes from the reporter's own diagnostics
download in ``docs/evidence/devcodes/analysis_697.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    is_setting_reading,
)
from custom_components.dessmonitor.device_support.device_registry import (
    is_devcode_supported,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

DEVCODE = 697

EVIDENCE = (
    Path(__file__).resolve().parent.parent / "docs/evidence/devcodes/analysis_697.json"
)

# The record's own identity. The integration publishes both as attributes.
ATTRIBUTE_TITLES = {"id", "Timestamp"}


def _device() -> dict[str, Any]:
    payload = json.loads(EVIDENCE.read_text("utf-8"))
    (device,) = payload["data"]["devices"]
    return device


def _resolved_key(title: str) -> str | None:
    mapped = apply_devcode_transformations(DEVCODE, {"title": title, "val": "1"})
    return resolve_sensor_key(mapped.get("title"), title)


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


@pytest.mark.parametrize(
    ("title", "expected_key"),
    [
        # The three the download reported as reaching no entity.
        ("Charger Current", "Charger Current"),
        ("Charger Power", "Charger Power"),
        ("Accumulated PV Power", "PV Cumulative Power Generation"),
        # A sample of the eighteen that already resolved, so a later change to
        # SENSOR_TYPES cannot take them away unnoticed.
        ("Battery Voltage", "Battery Voltage"),
        ("Batt Current", "Batt Current"),
        ("PV Voltage", "PV Voltage"),
        ("PLoad", "PLoad"),
        ("PInverter", "PInverter"),
        ("Accumulated Load Power", "Accumulated Load Power"),
        ("Accumulated Self_Use Power", "Accumulated Self_Use Power"),
        ("work state", "work state"),
        ("rated power", "rated power"),
    ],
)
def test_titles_resolve_to_their_sensor(title: str, expected_key: str) -> None:
    assert _resolved_key(title) == expected_key


def test_every_reading_in_the_download_reaches_an_entity() -> None:
    """The condition the Repairs card and the support status are built on."""
    unaccounted = [
        row["title"]
        for row in _device()["readings"]
        if _resolved_key(row["title"]) is None
        and row["title"] not in ATTRIBUTE_TITLES
        and not is_setting_reading(DEVCODE, row["title"])
    ]

    assert unaccounted == []


def test_the_charger_readings_are_measured_on_the_battery() -> None:
    """Why they keep the vendor's names instead of a PV or AC charging key.

    The download's own figures say which side the meter is on: the battery at
    49.0 V against a charger drawing 2.2 A and 108 W.
    """
    wanted = ("Battery Voltage", "Charger Current", "Charger Power")
    readings = {
        row["title"]: float(row["value"])
        for row in _device()["readings"]
        if row["title"] in wanted
    }

    product = readings["Battery Voltage"] * readings["Charger Current"]

    assert abs(product - readings["Charger Power"]) < 1.0
    assert _resolved_key("Charger Current") != "PV charging current"
    assert _resolved_key("Charger Power") != "PV Charge Power"


def test_the_profile_declares_no_setting() -> None:
    """None of the twenty-four control fields is repeated as a reading."""
    device = _device()
    readings = {row["title"] for row in device["readings"]}
    controls = {field["name"] for field in device["control_fields"]}

    assert readings & controls == set()


def _sensor_for(hass, point: dict[str, Any]):
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": DEVCODE, "alias": "Shed"},
                "data": [point],
            }
        },
    )
    (sensor,) = _build_sensor_entities(coordinator, set())
    return sensor


def test_the_lifetime_pv_counter_reaches_home_assistant(hass) -> None:
    sensor = _sensor_for(
        hass, {"title": "Accumulated PV Power", "val": "3920", "unit": "kWh"}
    )

    assert sensor.name == "Shed PV Cumulative Energy"
    assert sensor.native_unit_of_measurement == "kWh"
    assert sensor.state_class == "total_increasing"
    assert sensor.native_value == 3920


def test_the_charger_power_reaches_home_assistant(hass) -> None:
    sensor = _sensor_for(hass, {"title": "Charger Power", "val": "108", "unit": "W"})

    assert sensor.name == "Shed Charger Power"
    assert sensor.native_unit_of_measurement == "W"
    assert sensor.native_value == 108
