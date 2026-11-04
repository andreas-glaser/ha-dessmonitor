"""Sensor coverage of the committed CLI analysis reports.

Devcode 6514 was registered for one reported symptom (#35) and left the rest of
the collector's telemetry unmapped, which surfaced again as #56. These tests
read the analyses the reporters supplied and fail when a reading the collector
labels with a unit cannot reach Home Assistant as a sensor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    is_setting_reading,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key
from custom_components.dessmonitor.support_report import (
    normalized_reports,
    scale_disagreements,
)

ANALYSIS_FILES = sorted(
    Path(__file__)
    .resolve()
    .parent.parent.joinpath("docs/evidence")
    .rglob("analysis_*.json")
)

@pytest.mark.parametrize("path", ANALYSIS_FILES, ids=lambda path: path.stem)
def test_committed_analysis_is_intact(path: Path) -> None:
    """A committed analysis is the authority for a devcode's mappings.

    The CLI signs each report over its redacted contents, so a file edited
    after the fact no longer matches. Without this the mappings could be
    justified by evidence nobody can check.
    """
    for record in _records(path):
        assert record["checksum"], f"{path.name} carries no checksum"
        assert record["checksum_valid"], (
            f"{path.name} does not match its own checksum; regenerate it from "
            "the CLI or the diagnostics download rather than editing it by hand"
        )


def _records(path: Path) -> list[dict[str, Any]]:
    """Return one normalized record per device, for either committed shape.

    Evidence arrives as a CLI analysis or as a diagnostics download, and a
    devcode is guarded the same way whichever produced it (#60).
    """
    with path.open("r", encoding="utf-8") as handle:
        return normalized_reports(json.load(handle))


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
    for record in _records(path):
        _assert_every_reading_resolves(path, record)


def _assert_every_reading_resolves(path: Path, record: dict[str, Any]) -> None:
    """Fail when a reading that carries a unit reaches no sensor."""
    devcode = record["devcode"]
    units = dict(record["units"])

    excluded = DELIBERATELY_UNMAPPED.get(devcode, {})
    unmapped = {
        title: unit
        for title, unit in units.items()
        if title not in excluded
        and not is_setting_reading(devcode, title)
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
    for record in _records(path):
        devcode = record["devcode"]
        for title in DELIBERATELY_UNMAPPED.get(devcode, {}):
            assert title in record["titles"], (
                f"devcode {devcode} no longer reports {title!r}; remove the "
                "exclusion in DELIBERATELY_UNMAPPED"
            )
            assert (
                resolve_sensor_key(
                    apply_devcode_transformations(devcode, {"title": title}).get(
                        "title"
                    ),
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


def test_a_diagnostics_report_is_guarded_like_a_cli_analysis() -> None:
    """Either shape can be committed as evidence for a devcode (#60).

    A diagnostics download records a unit for every reading, where a CLI
    analysis records one for the sampled readings only, so committing one of
    those closes the blind spot in this guard rather than widening it.
    """
    from custom_components.dessmonitor.support_report import build_support_report

    readings = [
        {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
        {"title": "Daily Generation", "val": "10.2", "unit": "kWh"},
        {"title": "Protocol Number", "val": "3", "unit": ""},
    ]
    report = build_support_report(devcode=6515, readings=readings)

    (record,) = normalized_reports({"devices": [report]})

    assert record["devcode"] == 6515
    assert record["source"] == "integration_diagnostics"
    assert record["checksum_valid"] is True
    assert record["units"] == {"Battery Voltage": "V", "Daily Generation": "kWh"}
    assert "Protocol Number" in record["titles"]

    # And the guard still catches the dropped reading in it.
    with pytest.raises(AssertionError, match="Daily Generation"):
        _assert_every_reading_resolves(Path("downloaded.json"), record)


def test_an_edited_report_fails_its_checksum() -> None:
    from custom_components.dessmonitor.support_report import build_support_report

    report = build_support_report(
        devcode=6515, readings=[{"title": "SOC", "val": "37", "unit": "%"}]
    )
    report["devcode"] = 6544

    (record,) = normalized_reports(report)

    assert record["checksum_valid"] is False


def test_a_diagnostics_download_is_read_as_home_assistant_writes_it() -> None:
    """Home Assistant wraps a diagnostics report under ``data`` (#62).

    That envelope, not the bare report, is what a reporter attaches to an
    issue, and the coverage tooling rejected every one of those files as "not a
    devcode analysis or support report".
    """
    from custom_components.dessmonitor.support_report import build_support_report

    report = build_support_report(
        devcode=684,
        readings=[
            {"title": "today energy", "val": "7.65", "unit": "kWh"},
            {"title": "work mode", "val": "normal", "unit": ""},
        ],
    )

    for payload in (
        # The config-entry hook, which reports every device on the account.
        {"home_assistant": {"version": "2026.10.4"}, "data": {"devices": [report]}},
        # The per-device hook, which reports one.
        {"home_assistant": {"version": "2026.10.4"}, "data": report},
    ):
        (record,) = normalized_reports(payload)

        assert record["devcode"] == 684
        assert record["source"] == "integration_diagnostics"
        assert record["checksum_valid"] is True
        assert record["units"] == {"today energy": "kWh"}


# Scale disagreements a committed file *records*, rather than ones the
# integration still has. A hybrid download carries the local reading and the
# cloud's own figure for the same sensor, so a file taken before a unit fix
# preserves the evidence of it. Each entry names the fix that closed it, and
# the test below removes the entry's excuse once the file no longer shows it.
RECORDED_DISAGREEMENTS: dict[tuple[int, str], str] = {
    (2452, "Energy Total"): (
        "taken before the PI18 ET unit fix: the local query answered in "
        "watt-hours against the cloud's kWh, 10104399 against 10104.399 (#53)"
    ),
}


@pytest.mark.parametrize("path", ANALYSIS_FILES, ids=lambda path: path.stem)
def test_two_sources_agree_on_the_scale_of_a_reading(path: Path) -> None:
    """A hybrid download measures the same reading twice; they must agree.

    `SENSOR_TYPES` declares a unit, local drivers emit numbers, and nothing
    compared the two until the PI18 lifetime energy counter was found reading a
    thousand times too high in a file we already had (#53). Where a committed
    download carries both a local reading and the cloud's parameter for one
    sensor, an order of magnitude between them is a unit mistake.
    """
    for device in _device_reports(path):
        devcode = device.get("devcode")
        for key, (local, cloud) in scale_disagreements(device).items():
            assert (devcode, key) in RECORDED_DISAGREEMENTS, (
                f"{path.name}: devcode {devcode} reports {key} as {local} "
                f"locally and {cloud} from the cloud. One of the two is scaled "
                "wrongly; fix the driver or the mapping, or record the entry in "
                "RECORDED_DISAGREEMENTS with the reason."
            )


def test_recorded_disagreements_still_describe_a_committed_file() -> None:
    """An entry must lose its excuse once the evidence stops showing it.

    Otherwise a stale entry keeps a real disagreement excused after someone
    replaces the file with one taken on fixed code.
    """
    seen: set[tuple[int, str]] = set()
    for path in ANALYSIS_FILES:
        for device in _device_reports(path):
            devcode = device.get("devcode")
            for key in scale_disagreements(device):
                seen.add((devcode, key))

    stale = sorted(set(RECORDED_DISAGREEMENTS) - seen)
    assert not stale, (
        f"no committed file shows these disagreements any more: {stale}. "
        "Remove them from RECORDED_DISAGREEMENTS."
    )


def _device_reports(path: Path) -> list[dict[str, Any]]:
    """Return the device reports in a committed diagnostics download.

    A CLI analysis has no second source to compare against, so it yields none.
    """
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    data = payload.get("data", payload)
    devices = data.get("devices") if isinstance(data, dict) else None
    return [device for device in devices or [] if isinstance(device, dict)]
