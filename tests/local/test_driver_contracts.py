"""What a local driver may emit, held against the sensor catalogue.

Two silent failures live at this boundary, and both have happened:

- A driver emits a value in one scale while the sensor declares another. The
  local path labels every value with the canonical unit from ``SENSOR_TYPES``
  rather than with the driver's own, so the number is published wearing the
  right label and nothing complains. The PI18 ``ET`` query did exactly that,
  in watt-hours on a kWh sensor, until the diagnostics in #53 showed it beside
  the cloud's own figure.
- A driver emits a title that resolves to no sensor key. The local coordinator
  drops such a point without a word, so a typo in a field table costs a
  reading and produces no error anywhere.

These tests need no hardware and no reporter: they compare the driver tables
with the catalogue they publish into.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.local.profile import (
    GS2_FIELDS,
    GS_FIELDS,
    PI18_GS_FIELDS,
    SENSOR_UNITS,
)
from custom_components.dessmonitor.local.smg_protocol4 import _FIELDS as SMG_FIELDS
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

# Titles the SMG decoder derives rather than reading from a register.
SMG_DERIVED_TITLES = (
    "Operating mode",
    "SOC",
    "Battery Charging Current",
    "Battery Discharge Current",
    "Energy Today",
    "Energy Total",
)

P17_TITLES = sorted(
    {field.title for field in (*GS_FIELDS, *GS2_FIELDS, *PI18_GS_FIELDS)}
    | set(SENSOR_UNITS)
)
SMG_TITLES = sorted({title for _address, title, _divisor in SMG_FIELDS} | set(SMG_DERIVED_TITLES))


@pytest.mark.parametrize("title", P17_TITLES + SMG_TITLES)
def test_every_emitted_title_reaches_a_sensor(title: str) -> None:
    """A title that resolves to nothing is dropped in silence."""
    assert resolve_sensor_key(title) is not None, (
        f"the local drivers emit {title!r}, which resolves to no sensor key, so "
        "the reading is discarded. Add a SENSOR_TYPES entry or correct the title."
    )


@pytest.mark.parametrize("title,unit", sorted(SENSOR_UNITS.items()))
def test_a_declared_driver_unit_matches_its_sensor(title: str, unit: str) -> None:
    """The driver's unit and the entity's unit are the same claim."""
    key = resolve_sensor_key(title)
    assert key is not None
    declared = str(SENSOR_TYPES[key].get("unit", ""))

    assert declared == unit, (
        f"the local driver emits {title!r} in {unit!r} while its sensor "
        f"({key!r}) publishes {declared!r}. One of the two is wrong, and the "
        "published value will carry the sensor's unit either way."
    )


def test_the_declaration_covers_everything_the_p17_driver_emits() -> None:
    """A field added without a unit declaration escapes the check above."""
    missing = sorted(
        field.title
        for field in (*GS_FIELDS, *GS2_FIELDS, *PI18_GS_FIELDS)
        if field.title not in SENSOR_UNITS
    )

    assert not missing, f"these fields declare no unit in SENSOR_UNITS: {missing}"
