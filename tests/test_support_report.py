"""The shared devcode support report (#60).

One builder serves the integration's diagnostics download and the contributor
CLI, so a report from either path classifies support, redacts identifiers and
signs itself the same way.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from custom_components.dessmonitor.support_report import (
    PARTIAL,
    REPORT_VERSION,
    SUPPORTED,
    UNSUPPORTED,
    build_support_report,
    is_identifier_name,
    report_checksum,
    short_identity,
)

SERIAL = "SN-0001-REPORTER"
COLLECTOR = "Q0000000000000"


def _readings() -> list[dict[str, object]]:
    return [
        {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
        {"title": "SOC", "val": "37", "unit": "%"},
        {"title": "Timestamp", "val": "2026-11-02 10:00:39", "unit": ""},
        {"title": "Protocol Number", "val": "3", "unit": ""},
        {"title": "Devise serial number", "val": SERIAL, "unit": ""},
    ]


def test_a_devcode_with_no_profile_is_unsupported() -> None:
    report = build_support_report(devcode=9999, readings=_readings())

    assert report["support"]["status"] == UNSUPPORTED
    assert report["support"]["profile"] is None
    assert report["support"]["known_inverters"] == []
    assert report["report_version"] == REPORT_VERSION


def test_a_profile_that_drops_a_unit_carrying_reading_is_partial() -> None:
    """The #56 shape: a profile exists, so nothing warns, and readings vanish."""
    readings = _readings() + [
        {"title": "Daily Generation", "val": "10.2", "unit": "kWh"}
    ]

    report = build_support_report(devcode=6515, readings=readings)

    assert report["support"]["status"] == PARTIAL
    assert report["support"]["unresolved_with_unit"] == [
        {"title": "Daily Generation", "unit": "kWh", "sample": "10.2"}
    ]
    assert report["support"]["profile"]
    assert "Maxsky EM11000 11kW 48V" in report["support"]["known_inverters"]


def test_a_profile_whose_readings_all_resolve_is_supported() -> None:
    report = build_support_report(devcode=6515, readings=_readings())

    assert report["support"]["status"] == SUPPORTED
    assert report["support"]["resolved"] == 2
    # Timestamp is published as an attribute of every sensor, so it is not a
    # reading that could reach one and is not counted among them.
    assert report["support"]["total"] == len(_readings()) - 1
    # Settings and identity fields are listed, not counted as dropped readings.
    assert "Protocol Number" in report["support"]["unresolved_without_unit"]


def test_a_reading_published_as_an_attribute_is_not_reported_as_dropped() -> None:
    """Timestamp becomes last_updated on every sensor, so it is not missing."""
    report = build_support_report(devcode=6515, readings=_readings())

    assert "Timestamp" not in report["support"]["unresolved_without_unit"]
    assert all(
        item["title"] != "Timestamp"
        for item in report["support"]["unresolved_with_unit"]
    )


def test_every_reading_records_its_unit_and_what_it_resolves_to() -> None:
    """A CLI analysis keeps a unit for the first twenty readings only (#60)."""
    readings = [
        {"title": f"Battery Voltage", "val": "53.1", "unit": "V"},
        *(
            {"title": f"Filler {index}", "val": str(index), "unit": "W"}
            for index in range(30)
        ),
        {"title": "SOC", "val": "37", "unit": "%"},
    ]

    report = build_support_report(devcode=6515, readings=readings)

    assert len(report["readings"]) == 32
    assert all(row["unit"] for row in report["readings"])
    assert report["readings"][0]["resolved_key"] == "Battery Voltage"
    assert report["readings"][-1]["resolved_key"] == "SOC"
    assert report["readings"][1]["resolved_key"] is None


def test_identifiers_are_hashed_and_their_values_blanked() -> None:
    report = build_support_report(
        devcode=6515,
        readings=_readings(),
        device_serial=SERIAL,
        collector_product_number=COLLECTOR,
    )

    serialized = json.dumps(report)
    assert SERIAL not in serialized
    assert COLLECTOR not in serialized
    assert report["device_identity"] == short_identity(SERIAL)
    assert report["collector_identity"] == short_identity(COLLECTOR)
    assert report["device_identity"].startswith("sha256:")


def test_the_same_device_hashes_to_the_same_identity_across_reports() -> None:
    """Two downloads must be correlatable without disclosing a serial."""
    first = build_support_report(devcode=6515, readings=[], device_serial=SERIAL)
    second = build_support_report(devcode=6515, readings=[], device_serial=SERIAL)

    assert first["device_identity"] == second["device_identity"]
    assert first["device_identity"] != short_identity("SN-0002-REPORTER")


def test_control_and_local_sections_appear_only_when_supplied() -> None:
    bare = build_support_report(devcode=6515, readings=_readings())
    assert "control_fields" not in bare
    assert "parameters" not in bare
    assert "local" not in bare

    full = build_support_report(
        devcode=6515,
        readings=_readings(),
        control_fields={"Output priority": {"type": "options", "id": "los_output_"}},
        parameters={"Battery Current": {"val": "1.2"}},
        local={"driver": "pi30", "sensor_count": 34},
    )
    assert full["control_fields"][0]["name"] == "Output priority"
    assert full["parameters"][0]["name"] == "Battery Current"
    assert full["local"] == {"driver": "pi30", "sensor_count": 34}


def test_the_checksum_covers_the_report_it_ships_with() -> None:
    report = build_support_report(devcode=6515, readings=_readings())

    assert report["checksum"] == report_checksum(report)

    edited = dict(report)
    edited["devcode"] = 6544
    assert edited["checksum"] != report_checksum(edited)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Devise serial number", True),
        ("Device Serial Number", True),
        ("id", True),
        ("collector alias", True),
        ("token", True),
        ("Battery Voltage", False),
        ("Grid frequency", False),
    ],
)
def test_identifier_names_are_recognized(name: str, expected: bool) -> None:
    assert is_identifier_name(name) is expected


def test_the_module_loads_without_the_integration_package() -> None:
    """The contributor CLI loads this file by path, with no Home Assistant.

    Importing `custom_components.dessmonitor` runs the integration's package
    init, which imports Home Assistant, and a reporter installs only the CLI's
    own requirements.
    """
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "dessmonitor"
        / "support_report.py"
    )
    spec = importlib.util.spec_from_file_location("standalone_support_report", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.is_identifier_name("Devise serial number") is True
    assert module.short_identity(SERIAL) == short_identity(SERIAL)
    assert module.analysis_checksum({"devcode": 6515})


def test_the_counts_describe_one_population() -> None:
    """"Maps N of M readings" has to be arithmetic a reader can check.

    ``resolved`` counted distinct entity keys while ``total`` counted raw
    rows, so a collector that reports one title twice - devcode 2376 repeats
    "Output frequency" and "Battery Current" - looked as if readings were
    being dropped, in the diagnostics file and in the Repairs card text
    (#60). Rows that reach an entity, plus rows that reach nothing, are now
    the readings counted.
    """
    readings = [
        {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
        # The same reading twice: two rows, one entity.
        {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
        {"title": "SOC", "val": "37", "unit": "%"},
        {"title": "Protocol Number", "val": "3", "unit": ""},
        # Published as an attribute, so not a reading that could reach one.
        {"title": "Timestamp", "val": "2026-11-02 10:00:39", "unit": ""},
    ]

    support = build_support_report(devcode=6515, readings=readings)["support"]

    unresolved_rows = sum(
        1 for row in build_support_report(devcode=6515, readings=readings)["readings"]
        if not row["resolved_key"] and row["title"] != "Timestamp"
    )
    assert support["resolved"] == 3
    assert support["total"] == 4
    assert support["total"] - support["resolved"] == unresolved_rows
    # The entities those readings reach, which is the smaller number.
    assert support["sensors"] == 2
