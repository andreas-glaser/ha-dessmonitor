"""Devcode 752 on a Kstar KSG 5K DM, which arrived with no profile (#95).

Five of its thirty-two readings resolved through the generic fallback.
Twenty-two of the rest carry a unit, which is what held the Repairs card
open, and they include every figure the owner asked for: all three trackers,
the array total, the R-phase grid measurements, the heatsink, the DC bus, the
lifetime energy counter and the day's peak output.

The reported defect was the energy sensors: ``Total energy`` stood at 33057
kWh in the same payload where the plant summary's ``energyTotal`` read
``0.0000``, and the summary is what fed the sensor.

Every title and value asserted here comes from
``docs/evidence/devcodes/analysis_752.json``, which is the reporter's own
integration diagnostics download.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support.device_registry import (
    get_devcode_config,
    is_devcode_supported,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key
from custom_components.dessmonitor.support_report import resolved_key_for

DEVCODE = 752

EVIDENCE = (
    Path(__file__).resolve().parent.parent
    / "docs/evidence/devcodes/analysis_752.json"
)

# Three trackers, reported as "PVn input ...". The power per tracker reaches
# the MPPT keys rather than a "PVn Power" key: devcodes 4743 and 6544 send
# that title and 4743 declares its three absent, so a key of that name would
# give those installations sensors reading zero in daylight (#58).
PER_TRACKER = {
    "PV1 input voltage": "PV1 Voltage",
    "PV2 input voltage": "PV2 Voltage",
    "PV3 input voltage": "PV3 Voltage",
    "PV1 input current": "PV1 Current",
    "PV2 input current": "PV2 Current",
    "PV3 input current": "PV3 Current",
    "PV1 input power": "MPPT1 Power",
    "PV2 input power": "MPPT2 Power",
    "PV3 input power": "MPPT3 Power",
}

NEWLY_MAPPED = {
    "PV total input power": "PV Power",
    "PBUS voltage": "Positive Bus Voltage",
    "R phase grid voltage": "Grid Voltage",
    "R phase grid current": "grid current",
    "Radiator temperature": "Inverter Radiator Temperature",
    "Total energy": "Energy Total",
    "Today power peak": "Today Peak Power",
    "Operation mode": "Inverter Status",
}

# Carries no unit, so none of these held the Repairs card open, and none is a
# measurement. "Grid connected number" reads "031841", whose leading zero
# makes it a vendor string rather than a figure.
UNMAPPED_ON_PURPOSE = {"id", "Timestamp", "Serial number", "Grid connected number"}

# Fields the collector reports that this hardware never fills.
DECLARED_ABSENT = {
    "S phase grid voltage",
    "T phase grid voltage",
    "S phase grid current",
    "T phase grid current",
    "NBUS voltage",
    "Module temperature",
}


def _device() -> dict[str, Any]:
    payload = json.loads(EVIDENCE.read_text("utf-8"))
    devices = payload["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["devcode"] == DEVCODE
    return devices[0]


def _key(title: str) -> str | None:
    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def _value(title: str) -> str:
    return next(
        reading["value"]
        for reading in _device()["readings"]
        if reading["title"] == title
    )


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reading_that_carries_a_unit_reaches_a_sensor_or_is_declared() -> None:
    """What closes the Repairs card, and the reason the issue was opened."""
    absent = get_devcode_config(DEVCODE)["absent_readings"]
    unresolved = [
        reading["title"]
        for reading in _device()["readings"]
        if reading.get("unit")
        and not _key(reading["title"])
        and reading["title"] not in absent
    ]

    assert unresolved == []


def test_only_the_documented_readings_stay_unmapped() -> None:
    titles = {reading["title"] for reading in _device()["readings"]}

    assert {title for title in titles if not _key(title)} == (
        UNMAPPED_ON_PURPOSE | DECLARED_ABSENT
    )


@pytest.mark.parametrize(("title", "expected"), sorted(PER_TRACKER.items()))
def test_each_tracker_reaches_its_own_sensor(title: str, expected: str) -> None:
    assert _key(title) == expected


@pytest.mark.parametrize(("title", "expected"), sorted(NEWLY_MAPPED.items()))
def test_the_reported_gaps_are_closed(title: str, expected: str) -> None:
    assert _key(title) == expected


@pytest.mark.parametrize("title", sorted(DECLARED_ABSENT))
def test_an_unfilled_field_is_declared_rather_than_mapped(title: str) -> None:
    """A mapping here would publish a sensor reading zero for ever."""
    absent = get_devcode_config(DEVCODE)["absent_readings"]

    assert title in absent
    assert absent[title]
    assert _key(title) is None
    assert float(_value(title)) == 0.0


def test_the_array_total_is_in_watts_and_not_the_summary_kilowatts() -> None:
    """502 W against 298 + 204 from the two live trackers.

    Resolving this title onto the kilowatt ``outpower`` sensor by friendly
    name would publish it a thousand times high, which is what devcode 4743's
    "Total PV power" mapping exists to prevent.
    """
    total = float(_value("PV total input power"))

    assert total == pytest.approx(
        float(_value("PV1 input power")) + float(_value("PV2 input power")), abs=1
    )
    assert _key("PV total input power") == "PV Power"


def test_the_bus_is_a_single_rail() -> None:
    """375.2 V is a whole DC link on a 230 V single-phase inverter.

    Devcode 2548's split bus reports 409 V on each side. Mapping the negative
    rail here would publish a sensor this hardware has nothing to put in.
    """
    assert float(_value("PBUS voltage")) == 375.2
    assert float(_value("NBUS voltage")) == 0.0
    assert _key("PBUS voltage") == "Positive Bus Voltage"
    assert _key("NBUS voltage") is None


def test_the_zero_summary_total_does_not_publish_a_second_entity(hass) -> None:
    """Why the owner saw 0.0000 beside an inverter that had made 33057 kWh.

    The summary title and the device's own counter reach one sensor key, so
    the merge drops the summary point rather than publishing a second entity
    under the same name holding the vendor's unset zero (#58, #75).
    """
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": DEVCODE, "alias": "Roof"},
                "data": [
                    {"title": "Total energy", "val": "33057", "unit": "kWh"},
                    {"title": "energyTotal", "val": "0.0000", "unit": "kWh"},
                ],
            }
        },
    )

    sensors = _build_sensor_entities(coordinator, set())

    assert [sensor.name for sensor in sensors] == ["Roof Energy Total"]
    assert sensors[0].native_value == 33057.0


def test_the_mode_word_is_published_rather_than_discarded(hass) -> None:
    """"NORMAL" is a word, and a key read as a number discards it (#81)."""
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": DEVCODE, "alias": "Roof"},
                "data": [{"title": "Operation mode", "val": "NORMAL", "unit": ""}],
            }
        },
    )

    sensors = _build_sensor_entities(coordinator, set())

    assert [sensor.native_value for sensor in sensors] == ["NORMAL"]


def test_no_other_devcode_sends_the_title_the_new_key_is_named_for() -> None:
    """Title resolution ignores case and whitespace, so a key named after one
    collector's title reaches every other collector that sends it (#58)."""
    senders: dict[str, set[int]] = {}
    for path in sorted(EVIDENCE.parent.glob("analysis_*.json")):
        payload = json.loads(path.read_text("utf-8"))
        for device in payload.get("data", payload).get("devices") or []:
            for reading in device.get("readings", []):
                if resolve_sensor_key(reading["title"]) == "Today Peak Power":
                    senders.setdefault("Today Peak Power", set()).add(
                        device.get("devcode")
                    )

    assert senders == {}, senders
