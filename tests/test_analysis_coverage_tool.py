"""What the maintainer coverage report says about a device's own settings.

Classifying a new devcode's unresolved titles means deciding which of them are
the inverter's settings rather than readings being dropped, and a diagnostics
download already answers that: it carries the device's control template beside
its readings. These tests cover the part of the report that shows it (#61).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "analysis_coverage.py"
_EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "devcodes"


def _load_tool() -> Any:
    """Load the tool the way a maintainer runs it, by path.

    At module import, not inside a test: ``pytest-homeassistant-custom-component``
    rebinds ``custom_components`` to its own testing config once fixtures run, so
    a module that imports the integration has to be loaded during collection.
    """
    spec = importlib.util.spec_from_file_location("dessmonitor_coverage", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COVERAGE = _load_tool()


def test_a_declared_setting_is_marked_rather_than_counted_as_dropped() -> None:
    """Devcode 2477's setpoints must not read as readings reaching no entity."""
    unmapped = COVERAGE.report(_EVIDENCE / "analysis_2477.json")

    assert unmapped == 0


def test_control_fields_of_the_device_are_named_only_when_asked(
    capsys: Any,
) -> None:
    """The list answers a classification question, so it is opt-in.

    Most of a control template never arrives as a reading - a restore-defaults
    button has nothing to report - so printing it on every run buries the few
    names that matter under the ones that never could.
    """
    COVERAGE.report(_EVIDENCE / "analysis_2477.json")
    assert "Restore Defaults" not in capsys.readouterr().out

    COVERAGE.report(_EVIDENCE / "analysis_2477.json", show_controls=True)
    assert "Restore Defaults" in capsys.readouterr().out


def test_an_unresolved_title_that_is_a_control_is_marked_as_one(capsys: Any) -> None:
    """A title the same report lists as a control is a setting to declare."""
    record = {
        "devcode": 2477,
        "titles": ["Buzzer Alarm", "Some Unknown Reading"],
        "units": {},
        "controls": ["Buzzer Alarm"],
        "source": "integration_diagnostics",
    }

    COVERAGE._report_one(Path("download.json"), record)

    lines = {
        line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()
    }
    # Already declared a setting by the profile, which is the stronger claim.
    assert "Buzzer Alarm  (setting)" in lines
    assert "Some Unknown Reading" in lines


def test_a_control_is_marked_on_a_devcode_that_declares_nothing(capsys: Any) -> None:
    """The marker is what tells a reviewer which titles to declare.

    Without it the judgement is made from the reviewer's reading of a title's
    name, which is how a devcode's settings came to be counted as missing
    readings in the first place.
    """
    record = {
        "devcode": 9999,
        "titles": ["Buzzer Alarm", "Some Unknown Reading"],
        "units": {},
        "controls": ["Buzzer Alarm"],
        "source": "integration_diagnostics",
    }

    COVERAGE._report_one(Path("download.json"), record)

    lines = {
        line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()
    }
    assert "Buzzer Alarm  (control on this device)" in lines
    assert "Some Unknown Reading" in lines


def test_a_control_matching_a_resolved_reading_is_not_listed_as_unmatched() -> None:
    """A control named like a live reading is not a spelling to chase.

    Devcode 2477 reports Output Voltage both as a measurement and as a
    setpoint, and listing its control as unmatched would invite declaring the
    title a setting, which would take away the sensor.
    """
    result = COVERAGE.coverage(
        {
            "devcode": 2477,
            "titles": ["Output Voltage", "Battery Piece"],
            "units": {"Output Voltage": "V"},
            "controls": ["Output Voltage", "Restore Defaults"],
            "source": "integration_diagnostics",
        }
    )

    assert result.control_names == ["Restore Defaults"]


def test_a_cli_analysis_records_no_control_template() -> None:
    """Only a diagnostics download carries one, and the tool must not invent it."""
    result = COVERAGE.coverage(
        {
            "devcode": 2477,
            "titles": ["Buzzer Alarm"],
            "units": {},
            "source": "cli_analysis",
        }
    )

    assert result.controls == ()
    assert result.control_names == []
