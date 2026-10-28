"""Value mappings for devcode 6514, from the redacted analysis in #35.

The profile shipped for battery SOC only, so its priority and mode sensors
reported raw API codes. Each expectation below comes from the committed
analysis: the observed telemetry values and the collector's own control enums
bse_eybond_read_55 and bat_eybond_read_74.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import apply_devcode_transformations
from custom_components.dessmonitor.sensor import _build_sensor_entities


@pytest.mark.parametrize(
    "title,raw,expected",
    [
        ("Output Priority", "SBU", "Solar → Battery → Utility"),
        ("Output Priority", "SUB", "Solar → Utility → Battery"),
        ("Output Priority", "UTI", "Utility First"),
        ("Output Priority", "SOL", "Solar First"),
        ("Output Priority", "SUF", "Solar → Utility First"),
        ("Charger Source Priority", "OSO", "Only Solar"),
        ("Charger Source Priority", "SNU", "Solar and Utility"),
        # Meaning not established by the API, manual or an observed reading.
        ("Charger Source Priority", "CSO", "CSO"),
        ("Operating mode", "OffgridMode", "Off-grid Mode"),
        ("Operating mode", "Unrecognized mode", "Unrecognized mode"),
    ],
)
def test_observed_values_are_labelled(title: str, raw: str, expected: str) -> None:
    point = {"title": title, "val": raw, "unit": ""}
    assert apply_devcode_transformations(6514, point)["val"] == expected
    assert point["val"] == raw


@pytest.mark.parametrize(
    "title,raw,expected",
    [
        ("Output Priority", "SBU", "Solar → Battery → Utility"),
        ("Charger Source Priority", "OSO", "Only Solar"),
        ("Operating mode", "OffgridMode", "Off-grid Mode"),
    ],
)
def test_mapped_value_is_a_valid_enum_state(
    hass, title: str, raw: str, expected: str
) -> None:
    """A label the integration shows must be in the entity's option list."""
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": 6514, "alias": "Home"},
                "data": [{"title": title, "val": raw, "unit": ""}],
            }
        },
    )

    (sensor,) = _build_sensor_entities(coordinator, set())

    assert sensor.native_value == expected
    assert sensor.native_value in sensor.options
