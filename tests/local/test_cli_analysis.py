"""What the contributor CLI records as a reading and as a priority value.

The devcode 6515 report in #57 showed both classifications failing on the same
collector: ``Secondary Output Priority Start Time`` enumerated ``16:32`` as an
output priority, which ``generate_devcode_template`` then wrote into
OUTPUT_PRIORITY_MAPPING, and the input mode ``APL`` was recorded as a reading
carrying amperes. Both misled the devcode author rather than the integration,
which is why they survived until a reporter's own analysis contradicted itself.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_cli_module() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "cli" / "dessmonitor_cli.py"
    spec = importlib.util.spec_from_file_location("dessmonitor_analysis_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI = _load_cli_module()


@pytest.mark.parametrize(
    "title,expected",
    [
        # Values the enum is for.
        ("Main Output Priority", "output"),
        ("Current output priority", "output"),
        ("Secondary Output Priority", "output"),
        ("Charger Source Priority", "charger"),
        ("Current charging priority", "charger"),
        ("Secondary Charging Priority", "charger"),
        # Clock values on devcode 6515, reported as bse_eybond_read_52/53 and
        # bat_eybond_read_61/62. These are schedule boundaries, not codes.
        ("Secondary Output Priority Start Time", None),
        ("Secondary Output Priority End Time", None),
        ("Secondary Charging Priority Start Time", None),
        ("Secondary Charging Priority End Time", None),
        # Not a priority at all.
        ("Operating mode", None),
        ("Battery Voltage", None),
    ],
)
def test_priority_titles_are_bucketed(title: str, expected: str | None) -> None:
    assert CLI.priority_bucket(title) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("230V", "V"),
        ("50Hz", "Hz"),
        ("-10.5 A", "A"),
        ("3.93 kWh", "kWh"),
        ("2963 W", "W"),
        ("42 °C", "°C"),
        ("37%", "%"),
        # Settings whose text happens to contain a unit letter. Each of these
        # was recorded as a reading by the substring check.
        ("APL", None),
        ("Always on", None),
        ("Automatic restart after overload failure", None),
        ("Auto restart after over temperature failure", None),
        ("Mains Mode", None),
        ("SBU", None),
        ("OFF", None),
        # A schedule boundary and a calendar string are not measurements.
        ("16:32", None),
        ("2026-11-01 10:00:39", None),
        ("", None),
    ],
)
def test_only_a_number_with_a_unit_is_a_reading(
    value: str, expected: str | None
) -> None:
    assert CLI.observed_unit(value) == expected


def test_the_committed_6515_report_is_the_regression_case() -> None:
    """Tie the fix to the evidence that exposed it.

    The 6515 report was generated before this fix, so its own
    output_priorities and charger_priorities still carry clock values.
    Its title list is what the analyzer classified, and every schedule boundary
    in it is now excluded while the priorities that do carry codes remain.
    """
    path = (
        Path(__file__).parents[2]
        / "docs"
        / "evidence"
        / "devcodes"
        / "analysis_6515.json"
    )
    with path.open("r", encoding="utf-8") as handle:
        analysis = json.load(handle)["analysis"]

    recorded = analysis["output_priorities"] + analysis["charger_priorities"]
    assert [value for value in recorded if ":" in value], (
        "this report is kept because it reproduces the defect; regenerating it "
        "with the current CLI would remove the case"
    )

    titles = analysis["sensor_titles"]
    assert [title for title in titles if CLI.priority_bucket(title)] == [
        "Charger Source Priority",
        "Current charging priority",
        "Current output priority",
        "Main Output Priority",
        "Secondary Charging Priority",
        "Secondary Output Priority",
    ]
