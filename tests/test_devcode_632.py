"""Sensor mappings for devcode 632, from the redacted analysis in #58.

This grid-tie collector spells its lifetime counter ``energy_total``, which
resolved to nothing while ``Energy today`` resolved on its own. That is why the
reporter saw a working daily figure beside a total stuck at 0 kWh.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import apply_devcode_transformations
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

DEVCODE = 632


def _resolved_key(title: str) -> str | None:
    """Return the sensor key a raw title reaches through this devcode."""
    mapped = apply_devcode_transformations(DEVCODE, {"title": title, "val": "1"})
    return resolve_sensor_key(mapped.get("title"), title)


@pytest.mark.parametrize(
    "title,expected_key",
    [
        # The reading the issue was opened for, and the one that already worked.
        ("energy_total", "Energy Total"),
        ("Energy today", "Energy Today"),
        # AC side, including the grid voltage the reporter asked for.
        ("Grid R voltage", "Grid Voltage"),
        ("Grid R current", "grid current"),
        ("Grid frequency", "Grid Frequency"),
        ("Output Power", "Output Active Power"),
        ("Output S", "Output Apparent Power"),
        ("Output Q", "Output Reactive Power"),
        ("Output PF", "Power Factor"),
        ("Instrument power", "Meter Power"),
        # Strings and the DC bus.
        ("PV1 voltage", "PV1 Voltage"),
        ("PV1 current", "PV1 Current"),
        ("PV3 voltage", "PV3 Voltage"),
        ("PV3 current", "PV3 Current"),
        ("bus voltage", "Bus Voltage"),
        # Status and counters.
        ("Inverter status", "Inverter Status"),
        ("Waiting time", "Grid Reconnect Waiting Time"),
        ("cumulative time", "Operating Time"),
        # Temperatures.
        ("Internal radiator temperature", "Inverter Radiator Temperature"),
        ("Internal ambient temperature", "Ambient Temperature"),
    ],
)
def test_titles_resolve_to_their_sensor(title: str, expected_key: str) -> None:
    assert _resolved_key(title) == expected_key


def _sensor_for(hass, point: dict[str, Any]):
    """Build the single entity this collector would publish for one reading."""
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": DEVCODE, "alias": "Roof"},
                "data": [point],
            }
        },
    )
    (sensor,) = _build_sensor_entities(coordinator, set())
    return sensor


def test_energy_total_reaches_home_assistant(hass) -> None:
    sensor = _sensor_for(
        hass, {"title": "energy_total", "val": "5289", "unit": "kWh"}
    )

    assert sensor.name == "Roof Energy Total"
    assert sensor.native_unit_of_measurement == "kWh"
    assert sensor.native_value == 5289


def test_inverter_status_is_not_an_enum_sensor(hass) -> None:
    """The vendor's status text is free-form, so it must not be an enum state.

    An enum sensor rejects a value outside its option list, and this collector
    reports words such as ``Normal`` that the battery inverters' operating-mode
    options do not contain.
    """
    sensor = _sensor_for(hass, {"title": "Inverter status", "val": "Normal", "unit": ""})

    assert sensor.native_value == "Normal"
    assert sensor.device_class != "enum"
    assert sensor.options is None


def test_the_idle_phases_withdraw_the_missing_reading_card() -> None:
    """The check that decides whether the Repairs card stays up.

    On 2.7.0 this collector's S and T phases and its three line voltages all
    carry a unit and all read 0.0, and the reporter was told seven readings
    were missing while every reading their inverter fills reached an entity
    (#58). Mapping them would publish five voltage sensors and two current
    sensors that read zero forever.
    """
    import json
    from pathlib import Path

    from custom_components.dessmonitor.support_report import build_support_report

    evidence = (
        Path(__file__).resolve().parents[1]
        / "docs/evidence/devcodes/analysis_632_single_phase.json"
    )
    with evidence.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    (device,) = [
        device for device in payload["data"]["devices"] if device["devcode"] == DEVCODE
    ]
    readings = [
        {"title": row["title"], "val": row["value"], "unit": row["unit"]}
        for row in device["readings"]
    ]

    support = build_support_report(devcode=DEVCODE, readings=readings)["support"]

    assert support["unresolved_with_unit"] == []
    assert support["status"] == "supported"
    assert support["excluded"]["declared_absent"] == 7
