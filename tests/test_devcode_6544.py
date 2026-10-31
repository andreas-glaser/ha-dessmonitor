"""Observed cloud mode spelling from the redacted ANJ-11KW-48V-W-P analysis."""

from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import apply_devcode_transformations
from custom_components.dessmonitor.sensor import _build_sensor_entities


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("OffgridMode", "Off-grid Mode"),
        ("Inverter Mode", "Off-grid Mode"),
        ("Bypass Mode", "Grid Mode"),
        ("Battery Mode", "Battery Mode"),
        ("Unrecognized mode", "Unrecognized mode"),
    ],
)
def test_observed_mode_and_existing_modes(raw, expected):
    point = {"title": "Operating mode", "val": raw, "unit": ""}
    assert apply_devcode_transformations(6544, point)["val"] == expected
    assert point["val"] == raw


def test_cloud_to_local_mode_has_same_state_and_entity_identity(hass):
    # Exact cloud spelling observed in analysis v3, 2026-10-13 22:35:18.
    point = {"title": "Operating mode", "val": "OffgridMode", "unit": ""}
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST": {
                "collector": {"pn": "TEST"},
                "device": {"devcode": 6544, "alias": "Home"},
                "data": [point],
            }
        },
    )
    (sensor,) = _build_sensor_entities(coordinator, set())
    identity = sensor.unique_id
    assert sensor.native_value == "Off-grid Mode"
    assert sensor.native_value in sensor.options
    point["val"] = "Off-grid Mode"  # Local protocol-4 mode 3.
    assert sensor.native_value == "Off-grid Mode"
    assert sensor.unique_id == identity
