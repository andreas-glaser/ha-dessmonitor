"""Tests for the contributor-facing read-only local probe."""

from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType

import pytest


def _load_probe_module() -> ModuleType:
    """Load the standalone tool the same way a contributor executes it."""
    path = Path(__file__).parents[2] / "tools" / "cli" / "local_probe.py"
    spec = importlib.util.spec_from_file_location("dessmonitor_test_local_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_identifiers_are_redacted_by_default() -> None:
    """Reports are shareable without exposing collector or inverter IDs."""
    probe = _load_probe_module()
    redacted = probe._identifier("PRIVATE-SERIAL", include_identifiers=False)
    assert redacted.startswith("sha256:")
    assert "PRIVATE-SERIAL" not in redacted
    assert probe._identifier("PRIVATE-SERIAL", include_identifiers=True) == (
        "PRIVATE-SERIAL"
    )


def test_probe_report_is_private_and_rejects_symlinks(tmp_path: Path) -> None:
    """A local report is mode 0600 and cannot overwrite a symlink target."""
    probe = _load_probe_module()
    report_path = tmp_path / "probe.json"
    probe._write_private_report(report_path, {"safety": "read_only"})
    assert json.loads(report_path.read_text()) == {"safety": "read_only"}
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600

    target = tmp_path / "target.json"
    target.write_text("untouched")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises((OSError, ValueError)):
        probe._write_private_report(link, {"changed": True})
    assert target.read_text() == "untouched"


def test_probe_loads_each_registered_read_only_driver() -> None:
    """The standalone loader sees the same extensible driver registry as HA."""
    probe = _load_probe_module()
    drivers = probe._load_local_module("drivers")
    assert [driver.key for driver in drivers.DRIVERS] == ["p17", "smg_modbus"]
