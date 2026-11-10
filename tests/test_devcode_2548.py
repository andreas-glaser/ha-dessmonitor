"""Devcode 2548, an SPI-12K-H3 three-phase hybrid inverter (#67).

The first three-phase unit with a profile. Its collector names the phases two
ways at once - phase A by name, the other two prefixed "L2:" and "L3:" - and
separates the inverter's own output current from what the load draws, so these
tests pin the phase naming and that separation rather than only the counts.

Evidence is ``docs/evidence/devcodes/analysis_2548.json``, the reporter's own
diagnostics download, whose checksum the coverage guard verifies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.device_support.device_registry import (
    apply_devcode_transformations,
    is_devcode_supported,
)
from custom_components.dessmonitor.support_report import (
    build_support_report,
    resolved_key_for,
)

DEVCODE = 2548
EVIDENCE = (
    Path(__file__).resolve().parents[1]
    / "docs/evidence/devcodes/analysis_2548.json"
)


def _readings() -> list[dict[str, Any]]:
    with EVIDENCE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    for device in payload["data"]["devices"]:
        if device["devcode"] == DEVCODE:
            return [
                {"title": row["title"], "val": row["value"], "unit": row["unit"]}
                for row in device["readings"]
            ]
    raise AssertionError("the committed evidence has no devcode 2548 device")


def _key(title: str) -> str | None:
    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reading_the_collector_labels_reaches_a_sensor() -> None:
    """The check that decides whether the Repairs card stays up.

    The reporter's download resolved 14 of its 74 readings and named 49 that
    carry a unit and reached nothing.
    """
    support = build_support_report(devcode=DEVCODE, readings=_readings())["support"]

    assert support["unresolved_with_unit"] == []
    assert support["status"] == "supported"
    assert support["resolved"] == 65


def test_phase_a_is_l1() -> None:
    """One naming for all three phases, whichever style the vendor used."""
    assert _key("Inverter A phase voltage") == "Output L1 Voltage"
    assert _key("L2:Output voltage") == "Output L2 Voltage"
    assert _key("L3:Output voltage") == "Output L3 Voltage"
    assert _key("A phase load rate") == "Load L1 Percentage"
    assert _key("L2:Load rate") == "Load L2 Percentage"
    assert _key("L3:Load rate") == "Load L3 Percentage"


def test_the_inverter_current_and_the_load_current_are_separate_sensors() -> None:
    """They differ whenever the unit runs on bypass."""
    assert _key("Inverter A phase current") == "Output L1 Current"
    assert _key("L2:Inverting current") == "Output L2 Current"
    assert _key("L3:Inverting current") == "Output L3 Current"
    assert _key("Load A phase current") == "Load L1 Current"
    assert _key("L2:Load current") == "Load L2 Current"
    assert _key("L3:Load current") == "Load L3 Current"
    assert len({
        _key("Inverter A phase current"),
        _key("Load A phase current"),
    }) == 2


def test_the_mains_is_published_per_phase() -> None:
    """This unit reports no single combined mains voltage."""
    assert _key("L1:Mains voltage") == "Grid L1 Voltage"
    assert _key("L2:Mains voltage") == "Grid L2 Voltage"
    # The vendor lower-cases "mains" on the third phase only.
    assert _key("L3:mains voltage") == "Grid L3 Voltage"


def test_the_battery_energy_counters_arrive_in_watt_hours() -> None:
    """The sensors publish kilowatt-hours; the collector labels them Wh."""
    point = apply_devcode_transformations(
        DEVCODE,
        {"title": "battery energy total discharge", "val": "4768291.1", "unit": "Wh"},
    )

    assert point["title"] == "Battery Energy Total (Discharge)"
    # Binary floating point cannot hold 4768.2911 exactly, so compare to the
    # precision the figure carries rather than to the literal.
    assert point["val"] == pytest.approx(4768.2911)
    assert point["unit"] == "kWh"


def test_the_daily_generation_reaches_one_sensor_not_two() -> None:
    """It is the same figure the summary endpoint returns as energyToday.

    Both read 3.7 kWh in the download, so resolving them to one key keeps the
    device from publishing the quantity twice.
    """
    assert _key("PV power generation on the day") == "Energy Today"
    assert _key("energyToday") == "energyToday"
    assert SENSOR_TYPES["Energy Today"]["name"] == SENSOR_TYPES["energyToday"]["name"]


def test_the_summed_phase_voltage_is_not_published_as_an_output_voltage() -> None:
    """690.1 V is the three phases added up, and no phase reads that."""
    assert _key("Total output voltage") == "Total Output Voltage"
    assert SENSOR_TYPES["Total Output Voltage"]["entity_category"] == "diagnostic"


def test_the_machine_state_reaches_the_operating_mode_sensor() -> None:
    """Its value is left as the collector spells it.

    "contravariant" is the collector's own English and nothing in the download
    says which canonical mode it is, so it is published rather than guessed
    at. An unregistered enum state no longer takes the sensor down.
    """
    point = apply_devcode_transformations(
        DEVCODE,
        {"title": "The current state of the machine", "val": "contravariant"},
    )

    assert point["title"] == "Operating mode"
    assert point["val"] == "contravariant"


def test_the_identity_and_mode_texts_carry_no_unit() -> None:
    """So none of them holds the Repairs card open."""
    support = build_support_report(devcode=DEVCODE, readings=_readings())["support"]

    assert support["unresolved_without_unit"] == [
        "Battery type",
        "CPU1 version",
        "CPU2 version",
        "Energy saving mode",
        "Equipment type",
        "Input mode",
        "Output mode",
        "Product type",
        "System time",
    ]


def test_no_other_devcode_inherits_these_mappings() -> None:
    assert resolved_key_for(6515, {"title": "L3:Load rate", "val": "6"}) is None
    assert resolved_key_for(2477, {"title": "A phase load rate", "val": "3"}) is None
