"""Nameplate ratings and declared settings on devcode 2452, from #53.

This collector returns the inverter's nameplate ratings and its own setpoints
in the same call as the live readings. The ratings are facts about the hardware
and become diagnostic sensors; the setpoints are settings, five of them the
values of controls the account already publishes, and a profile declares those
so the support report stops counting them as readings that reach no entity.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    is_setting_reading,
)
from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

DEVCODE = 2452


def _resolved_key(title: str) -> str | None:
    """Return the sensor key a raw title reaches through this devcode."""
    mapped = apply_devcode_transformations(DEVCODE, {"title": title, "val": "1"})
    return resolve_sensor_key(mapped.get("title"), title)


@pytest.mark.parametrize(
    "title,expected_key",
    [
        ("AC output rating active power", "rated power"),
        ("AC output rating apparent power", "rated apparent power"),
        ("AC Output Rating Current", "rated current"),
        ("AC rated frequency", "rated frequency"),
        ("Battery Rating Voltage", "battery rated voltage"),
        ("Grid Rating Current", "grid rated current"),
    ],
)
def test_nameplate_ratings_reach_a_diagnostic_sensor(
    title: str, expected_key: str
) -> None:
    key = _resolved_key(title)

    assert key == expected_key
    assert SENSOR_TYPES[key]["entity_category"] == "diagnostic"


@pytest.mark.parametrize(
    "title",
    [
        # The five that are also controls on this account.
        "AC Output Rating Voltage",
        "Back To Discharge Voltage",
        "Battery bulk voltage",
        "Battery float voltage",
        # And the setpoints its control template does not advertise.
        "Battery recharge voltage",
        "Battery under voltage",
        "Low DC cut off voltage on second output",
    ],
)
def test_setpoints_are_declared_settings_rather_than_sensors(title: str) -> None:
    """A setting must not become a second entity for the same value."""
    assert is_setting_reading(DEVCODE, title) is True
    assert _resolved_key(title) is None


def test_a_declared_setting_matches_the_way_titles_are_compared() -> None:
    """Whitespace and case must not decide whether a setting is recognised."""
    assert is_setting_reading(DEVCODE, "  battery  bulk   voltage ") is True
    assert is_setting_reading(DEVCODE, "Battery Voltage") is False
