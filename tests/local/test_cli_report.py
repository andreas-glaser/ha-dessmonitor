"""The one-command contributor report.

A reporter following #57's thread ran five commands and had to pick the right
serial number out of two listings before they could attach anything. This
command does the enumeration itself, writes one redacted analysis per device,
and prints what the analysis covers, so the reporter learns what their own
hardware is missing without waiting for a maintainer.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

TOOLS = Path(__file__).parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# Imported at module scope on purpose. The coverage summary resolves titles
# through the integration packages, and importing them during collection is
# what keeps the Home Assistant test plugin's own custom_components package
# from shadowing this repository's. In a shell the CLI's lazy import is first
# and there is nothing to shadow it.
import analysis_coverage  # noqa: E402,F401


def _load_cli_module() -> ModuleType:
    for extra in (str(TOOLS / "cli"), str(TOOLS)):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    path = TOOLS / "cli" / "dessmonitor_cli.py"
    spec = importlib.util.spec_from_file_location("dessmonitor_report_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI = _load_cli_module()

SERIAL = "SN-REPORTER-0001"
ALIAS = "Reporter's shed"


def _analysis(devcode: int) -> dict[str, Any]:
    """An analysis in the shape analyze_device_for_devcode returns."""
    return {
        "api_profile": "dessmonitor_ess",
        "analysis_version": 3,
        "devcode": devcode,
        "device_sn": SERIAL,
        "collector_alias": ALIAS,
        "device_address": 1,
        "total_sensors": 4,
        "sensor_titles": [
            "Battery Voltage",
            "SOC",
            "Inverter inner temperature",
            "Timestamp",
        ],
        "operating_modes": [],
        "output_priorities": [],
        "charger_priorities": [],
        "potential_typos": [],
        "unit_patterns": {},
        "sample_data": [
            {"title": "Battery Voltage", "value": "50.4", "unit": "V"},
            {"title": "SOC", "value": "37", "unit": "%"},
            {"title": "Inverter inner temperature", "value": "47", "unit": "°C"},
            {"title": "Timestamp", "value": "2026-11-02 10:00:39", "unit": ""},
        ],
        "parameters": [],
        "control_field_count": 0,
        "control_fields": [],
        "parameter_count": 0,
        "checksum": "",
    }


def _cli(*, devcodes=(6515,)) -> MagicMock:
    """A signed-in client holding one collector with one device per devcode."""
    cli = MagicMock()
    cli.api_profile = "dessmonitor_ess"
    cli.config_file = Path(".dessmonitor_cli_config.json")
    cli.get_collectors = AsyncMock(return_value=[{"pn": "PN-0001"}])
    cli.get_devices = AsyncMock(
        return_value={
            "dev": [
                {"sn": f"{SERIAL}-{index}", "devcode": devcode, "devaddr": 1}
                for index, devcode in enumerate(devcodes)
            ]
        }
    )
    cli.analyze_device_for_devcode = AsyncMock(
        side_effect=[_analysis(devcode) for devcode in devcodes]
    )
    return cli


async def test_report_writes_one_redacted_analysis_per_device(tmp_path, capsys):
    cli = _cli()
    await CLI._run_report(cli, Namespace(output_dir=str(tmp_path)))

    (written,) = sorted(tmp_path.glob("*.json"))
    assert written.name == "analysis_6515.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    analysis = payload["analysis"]

    # Redacted, and the checksum recomputed over what is actually shared.
    assert analysis["device_sn"] == ""
    assert analysis["collector_alias"] == ""
    assert analysis["checksum"]
    assert SERIAL not in written.read_text(encoding="utf-8")
    assert ALIAS not in written.read_text(encoding="utf-8")

    out = capsys.readouterr().out
    assert "analysis_6515.json" in out
    assert "Attach these file(s) to your GitHub issue" in out


async def test_the_pasteable_summary_carries_no_identifier(tmp_path, capsys):
    """The reporter pastes this into a public issue."""
    cli = _cli()
    await CLI._run_report(cli, Namespace(output_dir=str(tmp_path)))

    summary = capsys.readouterr().out.split("Paste this summary into the issue:")[1]

    assert "devcode 6515" in summary
    assert "Inverter brand and model:" in summary
    assert "Collector model and firmware:" in summary
    assert SERIAL not in summary
    assert ALIAS not in summary
    assert "PN-0001" not in summary


async def test_report_tells_the_reporter_what_is_unmapped(tmp_path, capsys):
    """Coverage is the part a reporter cannot work out for themselves."""
    cli = _cli()
    await CLI._run_report(cli, Namespace(output_dir=str(tmp_path)))

    out = capsys.readouterr().out

    # Devcode 6515 is supported, and this collector reports one title that
    # resolves to nothing while carrying a unit.
    assert "already supported" in out
    assert "Inverter inner temperature" in out
    assert "[°C]" in out
    assert "worth mapping" in out


async def test_two_devices_on_one_devcode_do_not_overwrite_each_other(
    tmp_path, capsys
):
    cli = _cli(devcodes=(6515, 6515))
    await CLI._run_report(cli, Namespace(output_dir=str(tmp_path)))

    assert sorted(path.name for path in tmp_path.glob("*.json")) == [
        "analysis_6515.json",
        "analysis_6515_2.json",
    ]

    # Each summary line names its file. Four devices of one devcode otherwise
    # produced four identical lines, as a real account did.
    summary = capsys.readouterr().out.split("Paste this summary into the issue:")[1]
    assert "analysis_6515.json: devcode 6515" in summary
    assert "analysis_6515_2.json: devcode 6515" in summary


async def test_a_failing_device_does_not_lose_the_others(tmp_path, capsys):
    cli = _cli(devcodes=(6515, 6544))
    cli.analyze_device_for_devcode = AsyncMock(
        side_effect=[RuntimeError("device timed out"), _analysis(6544)]
    )

    await CLI._run_report(cli, Namespace(output_dir=str(tmp_path)))

    assert [path.name for path in tmp_path.glob("*.json")] == ["analysis_6544.json"]
    assert "analysis_6544.json" in capsys.readouterr().out


async def test_an_account_with_no_collector_writes_nothing(tmp_path, capsys):
    cli = _cli()
    cli.get_collectors = AsyncMock(return_value=[])

    await CLI._run_report(cli, Namespace(output_dir=str(tmp_path)))

    assert list(tmp_path.glob("*.json")) == []
    assert "No data collectors" in capsys.readouterr().out


@pytest.mark.parametrize(
    "devcode,expected", [(6515, "already supported"), (9999, "NOT YET SUPPORTED")]
)
def test_coverage_states_whether_the_devcode_has_a_profile(devcode, expected, capsys):
    CLI._print_coverage(_analysis(devcode))
    assert expected in capsys.readouterr().out
