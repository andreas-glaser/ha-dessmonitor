"""The shared resolver that maps vendor titles onto sensor definitions.

Both the cloud coordinator and the local poller go through this seam, so a
collector whose titles differ only in spacing or case is understood the same way
wherever its readings arrive from.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.const import SENSOR_TYPES
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


def test_no_two_sensor_definitions_differ_only_in_case_or_spacing() -> None:
    """One reading, one canonical key.

    `Grid Frequency` and `Grid frequency` were both defined, with identical
    configuration, the same display name and the same unique id. Nothing chose
    between them: whichever spelling a collector used became that entity's
    sensor type, which is how the cloud and a local driver ended up matching
    different raw titles for one reading (#53). A new pair would recreate that,
    and the resolver already ignores case and collapses whitespace, so the
    second entry can never be reached by a different route either.
    """
    by_normalized: dict[str, list[str]] = {}
    for key in SENSOR_TYPES:
        by_normalized.setdefault(normalize_sensor_title(key), []).append(key)

    duplicates = {
        normalized: keys
        for normalized, keys in by_normalized.items()
        if len(keys) > 1
    }

    assert not duplicates, (
        "these SENSOR_TYPES keys name one reading twice: "
        f"{duplicates}. Keep one and let the resolver match the other spelling."
    )
