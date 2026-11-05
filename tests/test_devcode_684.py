"""Sensor mappings for devcode 684, from the diagnostics download in #62.

This grid-tie collector reports the lower-cased Eybond title set devcode 518
also uses, so 31 of its 39 readings resolved to nothing: both strings, the grid
voltage and current, every temperature but one, the nameplate ratings and both
energy counters.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    get_all_operating_modes,
    map_operating_mode,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

DEVCODE = 684


def _resolved_key(title: str) -> str | None:
    """Return the sensor key a raw title reaches through this devcode."""
    mapped = apply_devcode_transformations(DEVCODE, {"title": title, "val": "1"})
    return resolve_sensor_key(mapped.get("title"), title)


@pytest.mark.parametrize(
    "title,expected_key",
    [
        # Energy counters, the readings a reporter notices first.
        ("today energy", "Energy Today"),
        ("total energy", "Energy Total"),
        # AC side. This inverter labels its single phase "A".
        ("grid voltage A", "Grid Voltage"),
        ("grid current A", "grid current"),
        ("grid frequency", "Grid Frequency"),
        ("output active power", "Output Active Power"),
        ("power factor", "Power Factor"),
        # Both strings.
        ("DC voltage 1", "PV1 Voltage"),
        ("DC voltage 2", "PV2 Voltage"),
        ("DC current 1", "PV1 Current"),
        ("DC current 2", "PV2 Current"),
        # Temperatures.
        ("radiator temperature", "Inverter Radiator Temperature"),
        ("inductor temperature", "Inductor Temperature"),
        ("inside temperature", "Inside Temperature"),
        ("transformer temperature", "Transformer temperature"),
        # Nameplate ratings.
        ("rate power", "rated power"),
        ("rate voltage", "rated voltage"),
        # Status.
        ("work mode", "Operating mode"),
    ],
)
def test_titles_resolve_to_their_sensor(title: str, expected_key: str) -> None:
    assert _resolved_key(title) == expected_key


@pytest.mark.parametrize(
    "title",
    [
        "fault information 1",
        "fault information 7",
        "safety regulation",
        "MPPT channel",
        "register number",
    ],
)
def test_bitmask_and_identity_fields_stay_unmapped(title: str) -> None:
    """These carry no unit and decoding them needs the vendor's fault table."""
    assert _resolved_key(title) is None


def test_the_observed_work_mode_is_an_allowed_state() -> None:
    """``normal`` is the only value the download shows, and it reads as itself.

    An enum sensor rejects a value its option list does not contain, so the
    mode would read unavailable without the mapping registering it.
    """
    assert map_operating_mode(DEVCODE, "normal") == "Normal"
    assert "Normal" in get_all_operating_modes()


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


def test_the_daily_counter_reaches_home_assistant(hass) -> None:
    sensor = _sensor_for(hass, {"title": "today energy", "val": "7.65", "unit": "kWh"})

    assert sensor.name == "Roof Energy Today"
    assert sensor.native_unit_of_measurement == "kWh"
    assert sensor.native_value == 7.65


def test_the_first_string_reaches_home_assistant(hass) -> None:
    sensor = _sensor_for(hass, {"title": "DC voltage 1", "val": "121.2", "unit": "V"})

    assert sensor.name == "Roof PV1 Voltage"
    assert sensor.native_unit_of_measurement == "V"
    assert sensor.native_value == 121.2
