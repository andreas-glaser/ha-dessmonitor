"""Devcode 659 on a Windon LT21HD, which arrived with no profile (#92).

Four of its forty-three readings resolved through the generic fallback.
Twenty-eight of the rest carry a unit, which is what held the Repairs card
open, and they include every figure the owner watches: all three phases, both
trackers, both energy counters and both heatsinks.

Like devcode 567 this collector leaves the plant summary's ``outpower``,
``energyToday`` and ``energyTotal`` at 0.0000 while reporting the real
figures itself, so Output Power and both energy sensors read zero on a
working inverter.

Every title and value asserted here comes from
``docs/evidence/devcodes/analysis_659.json``, which is the reporter's own
diagnostics download.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support.device_registry import (
    is_devcode_supported,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key
from custom_components.dessmonitor.support_report import resolved_key_for

DEVCODE = 659

EVIDENCE = (
    Path(__file__).resolve().parent.parent
    / "docs/evidence/devcodes/analysis_659.json"
)

# The three phases, which is what distinguishes this devcode from 567: it
# measures each one separately and reports a phase voltage, not a
# line-to-line one.
PER_PHASE = {
    "AC Side A Phase Voltage": "Grid L1 Voltage",
    "AC Side B Phase Voltage": "Grid L2 Voltage",
    "AC Side C Phase Voltage": "Grid L3 Voltage",
    "AC Side A Phase Current": "Grid L1 Current",
    "AC Side B Phase Current": "Grid L2 Current",
    "AC Side C Phase Current": "Grid L3 Current",
    "AC Side A Phase Frequency": "Grid L1 Frequency",
    "AC Side B Phase Frequency": "Grid L2 Frequency",
    "AC Side C Phase Frequency": "Grid L3 Frequency",
    "AC Side A Active Power": "Grid L1 Active Power",
    "AC Side B Active Power": "Grid L2 Active Power",
    "AC Side C Active Power": "Grid L3 Active Power",
    "AC Phase A Apparent Power": "Grid L1 Apparent Power",
    "AC Phase B Apparent Power": "Grid L2 Apparent Power",
    "AC Phase C Apparent Power": "Grid L3 Apparent Power",
}

# Two trackers, reported as "DC Input 1" and "DC Input 2".
PER_TRACKER = {
    "DC Input 1 Power": "MPPT1 Power",
    "DC Input 2 Power": "MPPT2 Power",
    "DC Input 1 Voltage": "PV1 Voltage",
    "DC Input 2 Voltage": "PV2 Voltage",
    "DC Input 1 current": "PV1 Current",
    "DC Input 2 current": "PV2 Current",
}

# The four keys named after the titles this collector already sends, so they
# resolve with no mapping at all.
RESOLVE_BY_THEIR_OWN_NAME = (
    "PV1 Insulation Resistance",
    "PV2 Insulation Resistance",
    "Radiator 1 Temperature",
    "Radiator 2 Temperature",
    "Automatic Startup",
)

# Raw vendor words with no table to decode them, firmware identity the single
# "Software version" key cannot hold three of, and the record's own identity.
UNMAPPED_ON_PURPOSE = {
    "id",
    "Timestamp",
    "SN",
    "MCU1(DSP) software version",
    "MCU2(ARM1) software version",
    "MCU3(ARM2) software version",
    "Debugging Information 1",
    "Debugging Information 2",
    "Debugging Information 3",
    "Debugging Information 4",
    "Debugging Information 5",
    "Debugging Information 6",
}


def _device() -> dict[str, Any]:
    payload = json.loads(EVIDENCE.read_text("utf-8"))
    devices = payload["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["devcode"] == DEVCODE
    return devices[0]


def _key(title: str) -> str | None:
    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def _reading(title: str) -> dict[str, Any]:
    return next(
        reading for reading in _device()["readings"] if reading["title"] == title
    )


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reading_that_carries_a_unit_reaches_a_sensor() -> None:
    """What closes the Repairs card, and the reason the issue was opened."""
    unresolved = [
        reading["title"]
        for reading in _device()["readings"]
        if reading.get("unit") and not _key(reading["title"])
    ]

    assert unresolved == []


def test_only_the_documented_readings_stay_unmapped() -> None:
    titles = {reading["title"] for reading in _device()["readings"]}

    assert {title for title in titles if not _key(title)} == UNMAPPED_ON_PURPOSE


@pytest.mark.parametrize(("title", "expected"), sorted(PER_PHASE.items()))
def test_each_phase_reaches_its_own_sensor(title: str, expected: str) -> None:
    assert _key(title) == expected


@pytest.mark.parametrize(("title", "expected"), sorted(PER_TRACKER.items()))
def test_each_tracker_reaches_its_own_sensor(title: str, expected: str) -> None:
    assert _key(title) == expected


@pytest.mark.parametrize("title", RESOLVE_BY_THEIR_OWN_NAME)
def test_a_key_named_after_the_title_needs_no_mapping(title: str) -> None:
    assert resolve_sensor_key(title) == title
    assert _key(title) == title


def test_the_phase_voltage_is_not_treated_as_a_line_voltage() -> None:
    """234.1 V is 400 V divided by the square root of three.

    Devcode 567 reports 404 V between phases and reaches the L1-L2 keys. On
    this devcode the same reading would be wrong by that factor, which is why
    the two profiles map their three voltages differently.
    """
    assert _reading("AC Side A Phase Voltage")["value"] == "234.1"
    assert _key("AC Side A Phase Voltage") == "Grid L1 Voltage"
    assert resolve_sensor_key("Grid L1-L2 Voltage") == "Grid L1-L2 Voltage"
    assert _key("AC Side A Phase Voltage") != "Grid L1-L2 Voltage"


def test_the_three_phase_powers_sum_to_the_total() -> None:
    """Evidence that the per-phase figures and the total are what they say.

    333 + 332 + 319 = 984, which is the reported "AC total Active Power", so
    mapping the total onto Output Power and the three onto their own sensors
    does not publish the same watts twice under one name.
    """
    phases = sum(
        float(_reading(title)["value"])
        for title in (
            "AC Side A Active Power",
            "AC Side B Active Power",
            "AC Side C Active Power",
        )
    )

    assert phases == float(_reading("AC total Active Power")["value"])


def test_apparent_power_is_at_least_active_power_on_each_phase() -> None:
    """The check behind publishing a "W"-labelled reading in volt-amperes.

    If the collector's label were right and these were watts, they would
    duplicate the active powers rather than exceed them.
    """
    for apparent, active in (
        ("AC Phase A Apparent Power", "AC Side A Active Power"),
        ("AC Phase B Apparent Power", "AC Side B Active Power"),
        ("AC Phase C Apparent Power", "AC Side C Active Power"),
    ):
        assert float(_reading(apparent)["value"]) > float(_reading(active)["value"])


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


def test_the_apparent_power_label_is_not_scaled_into_volt_amperes(hass) -> None:
    """No unit pair converts W to VA, so 366 is published as 366 VA."""
    sensor = _sensor_for(
        hass, {"title": "AC Phase A Apparent Power", "val": "366", "unit": "W"}
    )

    assert sensor.name == "Roof Grid L1 Apparent Power"
    assert sensor.native_unit_of_measurement == "VA"
    assert sensor.native_value == 366.0


def test_the_lifetime_counter_arrives_in_kilowatt_hours(hass) -> None:
    sensor = _sensor_for(
        hass, {"title": "Total Power Generation", "val": "79241.471", "unit": "kWh"}
    )

    assert sensor.name == "Roof Energy Total"
    assert sensor.native_unit_of_measurement == "kWh"
    assert sensor.native_value == 79241.471


def test_the_mode_word_is_published_rather_than_discarded(hass) -> None:
    """A state word offered to float() reads unknown for ever (#81)."""
    sensor = _sensor_for(hass, {"title": "mode inquiry", "val": "Grid", "unit": ""})

    assert sensor.native_value == "Grid"


def test_the_startup_word_is_published_rather_than_discarded(hass) -> None:
    sensor = _sensor_for(
        hass, {"title": "Automatic Startup", "val": "Automatically Boot", "unit": ""}
    )

    assert sensor.native_value == "Automatically Boot"


def test_the_zero_summary_figure_does_not_publish_a_second_entity(hass) -> None:
    """Why the owner saw zero beside a working inverter.

    The summary title and the device's own reading reach one sensor key, so
    the merge drops the summary point rather than publishing a second entity
    under the same name holding the vendor's unset 0.0000 (#58, #75).
    """
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": DEVCODE, "alias": "Roof"},
                "data": [
                    {"title": "AC total Active Power", "val": "984", "unit": "W"},
                    {"title": "outpower", "val": "0.0000", "unit": "kW"},
                ],
            }
        },
    )

    sensors = _build_sensor_entities(coordinator, set())

    assert [sensor.name for sensor in sensors] == ["Roof Output Power"]
    assert sensors[0].native_value == 984.0


def test_no_other_devcode_sends_the_titles_these_new_keys_are_named_for() -> None:
    """Title resolution ignores case and whitespace, so a key named after one
    collector's title reaches every other collector that sends it (#58)."""
    new_keys = set(PER_PHASE.values()) | set(RESOLVE_BY_THEIR_OWN_NAME)
    senders: dict[str, set[int]] = {}
    for path in sorted(EVIDENCE.parent.glob("analysis_*.json")):
        payload = json.loads(path.read_text("utf-8"))
        for device in payload.get("data", payload).get("devices") or []:
            for reading in device.get("readings", []):
                key = resolve_sensor_key(reading["title"])
                if key in new_keys:
                    senders.setdefault(key, set()).add(device.get("devcode"))

    assert all(devcodes == {DEVCODE} for devcodes in senders.values()), senders
