"""Preparing committed evidence from a reporter's diagnostics download.

Doing this by hand means choosing which of Home Assistant's own sections to
strip and trusting that the per-device checksums survived. These tests pin the
choice: the integration's sections are kept verbatim, the host and config-entry
sections are dropped, and a report that no longer matches its checksum is
refused rather than committed as evidence of something it may not say.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from custom_components.dessmonitor.support_report import build_support_report

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "evidence_from_diagnostics.py"


def _load_tool() -> Any:
    """Load the tool the way a maintainer runs it, by path.

    At module import, not inside a test: ``pytest-homeassistant-custom-component``
    rebinds ``custom_components`` to its own testing config once fixtures run, so
    a module that imports the integration has to be loaded during collection.
    """
    spec = importlib.util.spec_from_file_location("evidence_from_diagnostics", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def _tool() -> Any:
    """Return the loaded tool."""
    return TOOL


def _download(**devices: Any) -> dict[str, Any]:
    """Build a download in the shape Home Assistant writes one."""
    reports = [
        build_support_report(
            devcode=devcode,
            readings=readings,
            device_serial=f"SN-{devcode}",
            collector_product_number="Q0000SECRETPN0",
        )
        for devcode, readings in devices.items()
    ]
    return {
        "home_assistant": {"version": "2026.10.4", "timezone": "Europe/Amsterdam"},
        "custom_components": {"hacs": {"version": "2.0.0"}},
        "integration_manifest": {"domain": "dessmonitor"},
        "issues": [{"issue_id": "devcode_support_2452"}],
        "setup_times": {"entry": 1.2},
        "data": {
            "integration": {"version": "2.7.0-rc.1", "local_mode": "prefer_local"},
            "entry_data": {"username": "**redacted**"},
            "entry_options": {"local_listen_ip": "private ipv4 in subnet 1"},
            "coordinator": {"cloud_revision": 4},
            "local": {"setup_errors": [], "transports": []},
            "devices": reports,
        },
    }


def _write(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "config_entry-dessmonitor-01ABC.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_the_evidence_keeps_what_describes_the_devcode(tmp_path: Path) -> None:
    tool = _tool()
    payload = _download(**{"2452": [{"title": "SOC", "val": "37", "unit": "%"}]})

    evidence = tool.evidence_from(payload)

    assert set(evidence) == {"data"}
    assert set(evidence["data"]) == {"integration", "coordinator", "local", "devices"}
    # The device report is the reporter's, untouched: its checksum covers it.
    assert evidence["data"]["devices"] == payload["data"]["devices"]


def test_the_host_and_entry_sections_are_dropped(tmp_path: Path) -> None:
    """None of them is evidence, and they name the instance and the account."""
    tool = _tool()
    payload = _download(**{"2452": [{"title": "SOC", "val": "37", "unit": "%"}]})

    serialized = json.dumps(tool.evidence_from(payload))

    for section in (
        "home_assistant",
        "custom_components",
        "integration_manifest",
        "issues",
        "setup_times",
        "entry_data",
        "entry_options",
    ):
        assert section not in serialized


def test_one_file_is_written_per_devcode(tmp_path: Path) -> None:
    tool = _tool()
    payload = _download(
        **{
            "2452": [{"title": "SOC", "val": "37", "unit": "%"}],
            "6515": [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}],
        }
    )
    evidence = tool.evidence_from(payload)
    out = tmp_path / "evidence"
    out.mkdir()

    written = tool.write_evidence(evidence, out)

    assert [path.name for path in written] == [
        "analysis_2452.json",
        "analysis_6515.json",
    ]
    for path in written:
        # Each file carries only its own devcode, and still verifies.
        committed = json.loads(path.read_text(encoding="utf-8"))
        (record,) = tool.normalized_reports(committed)
        assert record["checksum_valid"] is True
        assert not tool.verify(committed)


def test_existing_evidence_is_never_replaced_silently(tmp_path: Path) -> None:
    tool = _tool()
    payload = _download(**{"2452": [{"title": "SOC", "val": "37", "unit": "%"}]})
    evidence = tool.evidence_from(payload)
    out = tmp_path / "evidence"
    out.mkdir()
    tool.write_evidence(evidence, out)

    with pytest.raises(FileExistsError):
        tool.write_evidence(evidence, out)

    assert tool.write_evidence(evidence, out, force=True)


def test_an_edited_report_is_refused(tmp_path: Path) -> None:
    """Evidence that no longer matches its checksum proves nothing."""
    tool = _tool()
    payload = _download(**{"2452": [{"title": "SOC", "val": "37", "unit": "%"}]})
    payload["data"]["devices"][0]["readings"][0]["value"] = "99"

    problems = tool.verify(tool.evidence_from(payload))

    assert problems and "does not match its own checksum" in problems[0]


def test_something_that_is_not_a_download_is_rejected(tmp_path: Path) -> None:
    tool = _tool()

    with pytest.raises(ValueError, match="not a diagnostics download"):
        tool.evidence_from({"analysis": {"devcode": 2452}})

    with pytest.raises(ValueError, match="no devices"):
        tool.evidence_from({"data": {"integration": {}, "devices": []}})


def test_a_symlinked_download_is_refused(tmp_path: Path) -> None:
    """Downloads are untrusted input; read a regular file or nothing."""
    tool = _tool()
    real = _write(tmp_path, _download(**{"2452": []}))
    link = tmp_path / "link.json"
    link.symlink_to(real)

    with pytest.raises(ValueError, match="symbolic link"):
        tool.read_download(link)


def _device_download(devcode: Any, readings: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a download in the shape the device page's button writes one.

    Home Assistant offers "Download diagnostics" on each device as well as on
    the entry, and a reporter attaches whichever one they found. This shape
    carries one device's report under ``support_report``, beside the sections
    the device page displays.
    """
    return {
        "home_assistant": {"version": "2026.11.0", "timezone": "Europe/Prague"},
        "custom_components": {"hacs": {"version": "2.0.0"}},
        "integration_manifest": {"domain": "dessmonitor"},
        "setup_times": {"entry": 1.2},
        "data": {
            "device_info": {"device_code": devcode, "device_address": 1},
            "configuration": {},
            "status": {},
            "raw_data_points": len(readings),
            "summary": {"total_sensors_created": 1},
            "support_report": build_support_report(
                devcode=devcode,
                readings=readings,
                device_serial=f"SN-{devcode}",
                collector_product_number="Q0000SECRETPN0",
                source="device_diagnostics",
            ),
        },
    }


def test_a_device_download_is_accepted_as_evidence(tmp_path: Path) -> None:
    """The other "Download diagnostics" button is the same evidence.

    Four of the five files attached to the devcode issues open when this was
    written were device downloads, and every one cost a round trip asking the
    reporter for the entry download instead.
    """
    tool = _tool()
    payload = _device_download(2341, [{"title": "SOC", "val": "57", "unit": "%"}])

    evidence = tool.evidence_from(payload)

    assert tool.verify(evidence) == []
    assert tool._devcodes(evidence) == [2341]
    out = tmp_path / "evidence"
    out.mkdir()
    assert [path.name for path in tool.write_evidence(evidence, out)] == [
        "analysis_2341.json"
    ]


def test_a_device_download_keeps_no_host_sections(tmp_path: Path) -> None:
    tool = _tool()
    payload = _device_download(2341, [{"title": "SOC", "val": "57", "unit": "%"}])

    serialized = json.dumps(tool.evidence_from(payload))

    for section in ("home_assistant", "custom_components", "setup_times"):
        assert section not in serialized


def test_an_edited_device_download_is_refused(tmp_path: Path) -> None:
    """The checksum covers the report whichever button produced it."""
    tool = _tool()
    payload = _device_download(2341, [{"title": "SOC", "val": "57", "unit": "%"}])
    payload["data"]["support_report"]["readings"][0]["value"] = "99"

    problems = tool.verify(tool.evidence_from(payload))

    assert problems and "does not match its own checksum" in problems[0]


def test_a_second_download_for_a_devcode_is_committed_beside_the_first(
    tmp_path: Path,
) -> None:
    """Two reports are better evidence than one, so neither replaces the other.

    The devcode 6514 setting declarations were drawn from a 24 V unit and
    confirmed against a 48 V one on an unrelated account; committing both
    means a later change has to satisfy both.
    """
    tool = _tool()
    payload = _download(**{"6489": [{"title": "BMS SOC", "val": "75", "unit": "%"}]})
    evidence = tool.evidence_from(payload)
    out = tmp_path / "evidence"
    out.mkdir()
    tool.write_evidence(evidence, out)

    written = tool.write_evidence(evidence, out, suffix="mains_present")

    assert [path.name for path in written] == ["analysis_6489_mains_present.json"]
    assert sorted(path.name for path in out.iterdir()) == [
        "analysis_6489.json",
        "analysis_6489_mains_present.json",
    ]


def test_a_second_download_still_refuses_to_overwrite_its_own_name(
    tmp_path: Path,
) -> None:
    tool = _tool()
    payload = _download(**{"6489": [{"title": "BMS SOC", "val": "75", "unit": "%"}]})
    evidence = tool.evidence_from(payload)
    out = tmp_path / "evidence"
    out.mkdir()
    tool.write_evidence(evidence, out, suffix="mains_present")

    with pytest.raises(FileExistsError):
        tool.write_evidence(evidence, out, suffix="mains_present")
