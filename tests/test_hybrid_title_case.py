"""A reading the cloud and a local driver spell differently (#53).

Devcode 2452 reports `Grid frequency`; the PI18 profile emits `Grid Frequency`.
The hybrid overlay matches the two case-insensitively and keeps the local point,
title included, so the entity built from the cloud spelling stopped finding its
own value for as long as local telemetry flowed. The reporter's 10-second debug
log carries 352 of `No matching data point found for sensor ..._grid_frequency
(looking for: Grid frequency)`, and their history graph shows the sensor
reading only while the device had fallen back to cloud-only.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.local.hybrid import merge_cloud_and_local
from custom_components.dessmonitor.sensor import _build_sensor_entities

CLOUD_TITLE = "Grid frequency"
LOCAL_TITLE = "Grid Frequency"


def _coordinator(points: list[dict[str, object]], hass) -> MagicMock:
    return MagicMock(
        hass=hass,
        data={
            "SN": {
                "collector": {"pn": "PN"},
                "device": {"devcode": 2452, "devaddr": 1, "alias": "Solar"},
                "data": points,
            }
        },
    )


def _cloud(title: str = CLOUD_TITLE, value: str = "50.1") -> dict[str, object]:
    return {
        "SN": {
            "collector": {"pn": "PN"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Solar"},
            "data": [
                {"title": "Timestamp", "val": "2026-11-01 10:00:00", "unit": ""},
                {"title": title, "val": value, "unit": "Hz"},
            ],
        }
    }


def _local(title: str = LOCAL_TITLE, value: float = 49.9) -> dict[str, object]:
    return {
        "SN": {
            "collector": {"pn": "PN"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Solar"},
            "data": [{"title": title, "val": value, "unit": "Hz"}],
        }
    }


@pytest.mark.parametrize(
    "created_from,overlaid_with",
    [
        # The entity exists from the cloud spelling and local overlays it.
        (CLOUD_TITLE, LOCAL_TITLE),
        # And the reverse, for a device discovered while local was already up.
        (LOCAL_TITLE, CLOUD_TITLE),
    ],
)
def test_a_differently_spelled_overlay_still_reaches_its_entity(
    hass, created_from: str, overlaid_with: str
) -> None:
    (sensor,) = _build_sensor_entities(
        _coordinator([{"title": created_from, "val": "50.1", "unit": "Hz"}], hass),
        set(),
    )

    sensor.coordinator.data = merge_cloud_and_local(
        _cloud(created_from),
        _local(overlaid_with, 49.9),
        local_available=True,
    )

    assert sensor.native_value == 49.9


def test_the_overlay_keeps_one_point_for_the_reading(hass) -> None:
    """Otherwise two sensors would claim the same reading."""
    merged = merge_cloud_and_local(_cloud(), _local(), local_available=True)

    titles = [str(point["title"]).casefold() for point in merged["SN"]["data"]]

    assert titles.count("grid frequency") == 1
    assert merged["SN"]["data"][-1] == {
        "title": "Data Source",
        "val": "Local",
        "unit": "",
    }


def test_padded_and_mixed_case_titles_resolve_to_the_same_entity(hass) -> None:
    """The normalization rule is the project's: trim, collapse, ignore case."""
    (sensor,) = _build_sensor_entities(
        _coordinator([{"title": "Grid  frequency", "val": "50.1", "unit": "Hz"}], hass),
        set(),
    )

    sensor.coordinator.data = {
        "SN": {
            "collector": {"pn": "PN"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Solar"},
            "data": [{"title": " GRID FREQUENCY ", "val": 49.8, "unit": "Hz"}],
        }
    }

    assert sensor.native_value == 49.8


def test_an_unrelated_reading_still_does_not_match(hass) -> None:
    """Normalizing must not make one sensor answer for another's point."""
    (sensor,) = _build_sensor_entities(
        _coordinator([{"title": CLOUD_TITLE, "val": "50.1", "unit": "Hz"}], hass),
        set(),
    )

    sensor.coordinator.data = {
        "SN": {
            "collector": {"pn": "PN"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Solar"},
            "data": [{"title": "Output Frequency", "val": 50.0, "unit": "Hz"}],
        }
    }

    assert sensor.native_value is None
