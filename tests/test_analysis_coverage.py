"""Sensor coverage of the committed CLI analysis reports.

Devcode 6514 was registered for one reported symptom (#35) and left the rest of
the collector's telemetry unmapped, which surfaced again as #56. These tests
read the analyses the reporters supplied and fail when a reading the collector
labels with a unit cannot reach Home Assistant as a sensor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import apply_devcode_transformations
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

ANALYSIS_FILES = sorted(
    Path(__file__)
    .resolve()
    .parent.parent.joinpath("docs/evidence")
    .rglob("analysis_*.json")
)

_CLI = Path(__file__).resolve().parent.parent / "tools" / "cli"
if str(_CLI) not in sys.path:
    sys.path.insert(0, str(_CLI))

from evidence import analysis_checksum  # noqa: E402


@pytest.mark.parametrize("path", ANALYSIS_FILES, ids=lambda path: path.stem)
def test_committed_analysis_is_intact(path: Path) -> None:
    """A committed analysis is the authority for a devcode's mappings.

    The CLI signs each report over its redacted contents, so a file edited
    after the fact no longer matches. Without this the mappings could be
    justified by evidence nobody can check.
    """
    analysis = _load(path)
    stored = analysis.get("checksum")

    assert stored, f"{path.name} carries no checksum"
    assert stored == analysis_checksum(analysis), (
        f"{path.name} does not match its own checksum; regenerate it with the "
        "CLI rather than editing it by hand"
    )


def _load(path: Path) -> dict[str, Any]:
    """Return the analysis payload of a committed CLI report."""
    with path.open("r", encoding="utf-8") as handle:
        return dict(json.load(handle)["analysis"])


def _titles_with_units(analysis: dict[str, Any]) -> dict[str, str]:
    """Return observed units by raw title, which marks a title as a reading.

    A title without a unit is a setting, an identity field or a timestamp, and
    those reach Home Assistant through the number, select and button platforms.
    """
    units: dict[str, str] = {}
    for section, label in (("sample_data", "title"), ("parameters", "name")):
        for point in analysis.get(section, []):
            title = point.get(label)
            unit = (point.get("unit") or "").strip()
            if title and unit:
                units[str(title)] = unit
    return units


def _sensor_entities(devcode: int, points: list[dict[str, Any]], hass) -> list[Any]:
    """Build the sensor entities a device would publish for these data points."""
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": devcode, "alias": "Home"},
                "data": points,
            }
        },
    )
    return _build_sensor_entities(coordinator, set())


# Readings a collector labels with a unit but never populates. Mapping one
# publishes a sensor that reads zero forever, so each entry here is a decision
# with evidence behind it rather than a title nobody noticed.
DELIBERATELY_UNMAPPED: dict[int, dict[str, str]] = {
    4743: {
        title: (
            "the collector reports 0 while the string produces: 220.5 V and "
            "7.3 A on string 1 against a 1552 W total in this analysis, and "
            "265 V and 1.6 A against 424 W of export on live hardware (#58)"
        )
        for title in ("PV1 power", "PV2 power", "PV3 power")
    },
}


def test_analysis_reports_are_committed() -> None:
    assert ANALYSIS_FILES, "no analysis reports found under docs/evidence"


@pytest.mark.parametrize("path", ANALYSIS_FILES, ids=lambda path: path.stem)
def test_every_reading_with_a_unit_resolves_to_a_sensor(path: Path) -> None:
    analysis = _load(path)
    devcode = analysis["devcode"]
    units = _titles_with_units(analysis)

    excluded = DELIBERATELY_UNMAPPED.get(devcode, {})
    unmapped = {
        title: unit
        for title, unit in units.items()
        if title not in excluded
        and resolve_sensor_key(
            apply_devcode_transformations(devcode, {"title": title}).get("title"),
            title,
        )
        is None
    }

    assert not unmapped, (
        f"devcode {devcode} drops readings that carry a unit: {unmapped}. "
        "Map them in device_support/devcode_"
        f"{devcode}.py or add a SENSOR_TYPES entry."
    )


@pytest.mark.parametrize("path", ANALYSIS_FILES, ids=lambda path: path.stem)
def test_exclusions_still_describe_an_unmapped_reading(path: Path) -> None:
    """An exclusion must stop applying once the title is mapped.

    Otherwise a stale entry keeps a reading excluded after someone maps it, and
    the guard quietly stops watching a sensor that now exists.
    """
    analysis = _load(path)
    devcode = analysis["devcode"]
    for title in DELIBERATELY_UNMAPPED.get(devcode, {}):
        assert title in analysis["sensor_titles"], (
            f"devcode {devcode} no longer reports {title!r}; remove the "
            "exclusion in DELIBERATELY_UNMAPPED"
        )
        assert (
            resolve_sensor_key(
                apply_devcode_transformations(devcode, {"title": title}).get("title"),
                title,
            )
            is None
        ), (
            f"{title!r} now resolves for devcode {devcode}; remove the "
            "exclusion in DELIBERATELY_UNMAPPED"
        )


@pytest.mark.parametrize(
    "devcode,title,expected_key",
    [
        # Reported missing on devcode 6514 in #56.
        (6514, "Grid  Power", "Grid Power"),
        (6514, "Grid  Voltage", "Grid Voltage"),
        (6514, "Total Output Active Power", "Output Active Power"),
        (6514, "Total Output Aparent Power", "Output Apparent Power"),
        (6514, "Total Output Current", "Output Current"),
        (6514, "Total Load Percentage", "Load Percent"),
        (6514, "PV Charging Power", "PV Charge Power"),
        # Per-leg readings requested for 6544 in #42 and present on both.
        (6514, "Output L1 Active Power", "Output L1 Active Power"),
        (6514, "Output L2 Active Power", "Output L2 Active Power"),
        (6514, "Output L1 Aparent Power", "Output L1 Apparent Power"),
        (6514, "Output L2 Aparent Power", "Output L2 Apparent Power"),
        (6544, "Output L1 Active Power", "Output L1 Active Power"),
        (6544, "Output L2 Apparent Power", "Output L2 Apparent Power"),
        (6544, "Output L1 Voltage", "Output L1 Voltage"),
        (6544, "Output L2 Current", "Output L2 Current"),
        (6544, "Load L1 Percentage", "Load L1 Percentage"),
    ],
)
def test_dual_output_titles_resolve(
    devcode: int, title: str, expected_key: str
) -> None:
    mapped = apply_devcode_transformations(devcode, {"title": title}).get("title")
    assert resolve_sensor_key(mapped, title) == expected_key


def test_dual_output_device_publishes_both_legs(hass) -> None:
    """A collector reporting only per-leg and summed output gets both."""
    points = [
        {"title": "Grid  Power", "val": "311", "unit": "W"},
        {"title": "Total Output Active Power", "val": "121", "unit": "W"},
        {"title": "Output L1 Active Power", "val": "299", "unit": "W"},
        {"title": "Output L2 Active Power", "val": "290", "unit": "W"},
    ]

    entities = _sensor_entities(6514, points, hass)

    by_unique_id = {entity.unique_id: entity for entity in entities}
    assert set(by_unique_id) == {
        "TEST-SN_grid_power",
        "TEST-SN_output_active_power",
        "TEST-SN_output_l1_active_power",
        "TEST-SN_output_l2_active_power",
    }
    assert by_unique_id["TEST-SN_grid_power"].native_value == 311.0
    assert by_unique_id["TEST-SN_output_l1_active_power"].native_value == 299.0
    assert by_unique_id["TEST-SN_output_l2_active_power"].native_value == 290.0
    assert all(
        entity.native_unit_of_measurement == "W" for entity in by_unique_id.values()
    )


def test_existing_unique_ids_are_unchanged(hass) -> None:
    """Collapsing whitespace must not move an installed entity to a new id."""
    points = [
        {"title": "Grid Power", "val": "100", "unit": "W"},
        {"title": "Battery Voltage", "val": "53.3", "unit": "V"},
        {"title": "Output Active Power", "val": "121", "unit": "W"},
    ]

    entities = _sensor_entities(6514, points, hass)

    assert {entity.unique_id for entity in entities} == {
        "TEST-SN_grid_power",
        "TEST-SN_battery_voltage",
        "TEST-SN_output_active_power",
    }
