"""The shared resolver that maps vendor titles onto sensor definitions.

Both the cloud coordinator and the local poller go through this seam, so a
collector whose titles differ only in spacing or case is understood the same way
wherever its readings arrive from.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.sensor_titles import (
    normalize_sensor_title,
    resolve_sensor_key,
    sensor_unit,
)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Grid Power", "Grid Power"),
        ("Grid  Power", "Grid Power"),
        ("  Grid   Power  ", "Grid Power"),
        ("grid power", "Grid Power"),
        ("GRID POWER", "Grid Power"),
        ("Grid\tPower", "Grid Power"),
        # Resolves through the definition's friendly name.
        ("Solar Power", "PV Power"),
        ("Load Percentage", "Load Percent"),
        ("Not A Sensor", None),
        ("", None),
        (None, None),
    ],
)
def test_resolve_sensor_key(title: str | None, expected: str | None) -> None:
    assert resolve_sensor_key(title) == expected


def test_first_matching_candidate_wins() -> None:
    """A devcode-mapped title takes precedence over the raw one."""
    assert resolve_sensor_key("Battery Power", "Grid Power") == "Battery Power"
    assert resolve_sensor_key(None, "Grid Power") == "Grid Power"
    assert resolve_sensor_key("Not A Sensor", "Grid Power") == "Grid Power"


def test_a_canonical_key_beats_another_entrys_friendly_name() -> None:
    """ "Energy Today" is a key of its own and the friendly name of "energyToday"."""
    assert resolve_sensor_key("Energy Today") == "Energy Today"


def test_sensor_unit_uses_the_canonical_definition() -> None:
    assert sensor_unit("Grid  Power") == "W"
    assert sensor_unit("battery voltage") == "V"
    assert sensor_unit("Load L2 Percentage") == "%"
    assert sensor_unit("Not A Sensor") == ""


def test_normalize_sensor_title() -> None:
    assert normalize_sensor_title("  Output  L1   Voltage ") == "output l1 voltage"
