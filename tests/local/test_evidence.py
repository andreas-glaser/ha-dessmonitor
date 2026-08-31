"""Tests for combined cloud/local devcode evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_evidence_module() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "cli" / "evidence.py"
    spec = importlib.util.spec_from_file_location("dessmonitor_test_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _local_report(serial: str) -> dict:
    return {
        "report_version": 1,
        "safety": "read_only",
        "detected": {
            "profile": "smg_modbus",
            "tunnel_device_code": 1,
            "collector_address": 255,
        },
        "inverters": [
            {
                "address": 1,
                "serial": serial,
                "model": "SMG / Modbus (6200W)",
                "firmware": "",
                "sensor_count": 3,
                "sensors": {
                    "Output Active Power": 900,
                    "Grid Voltage": 230.1,
                    "State of Charge": 75,
                },
            }
        ],
    }


def test_combined_evidence_matches_identity_and_titles() -> None:
    """Known vendor synonyms produce reviewable, high-confidence suggestions."""
    evidence = _load_evidence_module()
    serial = "PRIVATE-SERIAL"
    serial_hash = hashlib.sha256(serial.encode()).hexdigest()[:12]
    cloud = {
        "analysis_version": 3,
        "devcode": 2376,
        "device_sn": serial,
        "device_identity": f"sha256:{serial_hash}",
        "collector_alias": "Private installation name",
        "sample_data": [
            {"title": "AC output active power", "value": 895, "unit": "W"},
            {"title": "Grid voltage", "value": 230, "unit": "V"},
            {"title": "Battery percentage", "value": 75, "unit": "%"},
        ],
    }
    combined = evidence.combine_evidence(
        cloud, _local_report(f"sha256:{serial_hash}")
    )

    assert combined["analysis_version"] == 4
    assert combined["device_sn"] == f"sha256:{serial_hash}"
    assert combined["collector_alias"] == "redacted"
    assert combined["local_evidence"]["identity_match"] == "matched"
    assert combined["suggested_sensor_title_mappings"] == {
        "AC output active power": "Output Active Power",
        "Battery percentage": "State of Charge",
        "Grid voltage": "Grid Voltage",
    }
    assert "device_sn" not in combined["checksum"]


def test_ambiguous_title_is_not_guessed() -> None:
    """A duplicate normalized title never creates an automatic mapping."""
    evidence = _load_evidence_module()
    matches = evidence.correlate_sensor_titles(
        [{"title": "Grid voltage"}],
        {"Grid Voltage": 230, "Grid-voltage": 231},
    )
    assert matches == []


def test_local_report_loader_is_bounded_and_rejects_symlink(
    tmp_path: Path,
) -> None:
    """Contributor evidence cannot be loaded through a link or without safety tags."""
    evidence = _load_evidence_module()
    report_path = tmp_path / "local.json"
    report_path.write_text(json.dumps(_local_report("sha256:test")))
    assert evidence.load_local_report(str(report_path))["safety"] == "read_only"

    link = tmp_path / "linked.json"
    link.symlink_to(report_path)
    with pytest.raises(ValueError, match="symbolic"):
        evidence.load_local_report(str(link))

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"report_version": 1, "inverters": [{}]}))
    with pytest.raises(ValueError, match="read-only"):
        evidence.load_local_report(str(invalid))
