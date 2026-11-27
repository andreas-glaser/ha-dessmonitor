"""Devcode 2394 on an MPPT24V-60A-5000W, which arrived with no profile (#94).

This collector reports the smallest vocabulary any committed download
carries: twelve titles, of which seven already resolved through the generic
fallback. The three that did not - the mains voltage, the mains frequency and
the one temperature - all carry a unit, which is what held the Repairs card
open.

Every title and value asserted here comes from
``docs/evidence/devcodes/analysis_2394.json``, which is the reporter's own
device diagnostics download.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.dessmonitor.device_support.device_registry import (
    is_devcode_supported,
)
from custom_components.dessmonitor.support_report import resolved_key_for

DEVCODE = 2394

EVIDENCE = (
    Path(__file__).resolve().parent.parent
    / "docs/evidence/devcodes/analysis_2394.json"
)

# The three readings the issue was opened for, and what each now reaches.
NEWLY_MAPPED = {
    "Input voltage": "Grid Voltage",
    "Input frequency": "Grid Frequency",
    "temperature": "INV Module Termperature",
}

# The record's own identity fields. Neither carries a unit, so neither held
# the Repairs card open and neither needs a sensor.
UNMAPPED_ON_PURPOSE = {"id", "Timestamp"}


def _device() -> dict[str, Any]:
    payload = json.loads(EVIDENCE.read_text("utf-8"))
    devices = payload["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["devcode"] == DEVCODE
    return devices[0]


def _key(title: str) -> str | None:
    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


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


@pytest.mark.parametrize(("title", "expected"), sorted(NEWLY_MAPPED.items()))
def test_the_reported_gap_is_closed(title: str, expected: str) -> None:
    assert _key(title) == expected


def test_the_mains_voltage_is_not_folded_onto_the_output() -> None:
    """Both read 219.0 V in the download, which is the trap in this payload.

    A collector whose input and output voltages agree is one running on mains
    passthrough. Mapping either onto the other would have published one
    sensor for two measurements that part company the moment the grid fails.
    """
    readings = {reading["title"]: reading["value"] for reading in _device()["readings"]}

    assert readings["Input voltage"] == readings["Output voltage"] == "219.0"
    assert _key("Input voltage") != _key("Output voltage")


def test_the_single_temperature_is_the_inverter_module_reading() -> None:
    """Devcode 6513 names its one temperature the same way and maps it here.

    The collector names no stage, so there is nothing to tell an AC radiator
    from a DC one, and inventing a distinction would put the figure on a
    sensor this hardware does not have.
    """
    assert _key("temperature") == "INV Module Termperature"
    assert _key("temperature") == resolved_key_for(
        6513, {"title": "Temperature", "val": "27.0"}
    )
