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


def test_a_record_without_a_control_template_gets_no_controls() -> None:
    """The tool must not invent one.

    Both report shapes carry the control template now - a CLI analysis records
    the fields without their readbacks - so what this asserts is the remaining
    case: a device the platform advertises no controls for, as devcode 684 is.
    """
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


def test_a_control_sitting_at_a_reading_s_value_is_offered_as_a_candidate(
    capsys: Any,
) -> None:
    """The judgement every ``SETTING_READINGS`` declaration rests on.

    The spellings differ on both sides, so the names cannot make the pairing:
    devcode 2449 reports "Battery Re-Charge Voltage" 44.0 V against a "Back to
    Grid Voltage" control reading 44.0 (#80). Both sides format the number
    their own way, which is why the comparison is numeric.
    """
    record = {
        "devcode": 9999,
        "titles": ["Battery Re-Charge Voltage"],
        "units": {"Battery Re-Charge Voltage": "V"},
        "values": {"Battery Re-Charge Voltage": "44.0"},
        "controls": ["Back to Grid Voltage", "Battery Cut-off Voltage"],
        "control_values": {
            "Back to Grid Voltage": "44",
            "Battery Cut-off Voltage": "42.0",
        },
        "source": "integration_diagnostics",
    }

    COVERAGE._report_one(Path("download.json"), record)

    out = capsys.readouterr().out
    assert "Back to Grid Voltage" in out
    assert "Battery Cut-off Voltage" not in out


def test_a_title_already_named_as_a_control_is_not_paired_again(capsys: Any) -> None:
    """The name match is the stronger claim, and two lines would say it twice."""
    record = {
        "devcode": 9999,
        "titles": ["Battery Type"],
        "units": {},
        "values": {"Battery Type": "Lib"},
        "controls": ["Battery Type"],
        "control_values": {"Battery Type": "Lib"},
        "source": "integration_diagnostics",
    }

    COVERAGE._report_one(Path("download.json"), record)

    out = capsys.readouterr().out
    assert "Battery Type  (control on this device)" in out
    assert "a setting to declare" not in out


def test_a_text_valued_setting_pairs_on_its_text() -> None:
    """A battery type or an input range is not a number, and still pairs."""
    result = COVERAGE.coverage(
        {
            "devcode": 9999,
            "titles": ["Input Range"],
            "units": {},
            "values": {"Input Range": "UPS"},
            "controls": ["AC Input Range"],
            "control_values": {"AC Input Range": "ups"},
            "source": "integration_diagnostics",
        }
    )

    assert result.controls_reading_the_same_value("Input Range") == [
        ("AC Input Range", "ups")
    ]


def test_a_reading_with_no_recorded_value_pairs_with_nothing() -> None:
    """A CLI analysis samples its values, and records no control readback."""
    result = COVERAGE.coverage(
        {
            "devcode": 9999,
            "titles": ["Battery Re-Charge Voltage"],
            "units": {"Battery Re-Charge Voltage": "V"},
            "controls": ["Back to Grid Voltage"],
            "source": "cli_analysis",
        }
    )

    assert result.controls_reading_the_same_value("Battery Re-Charge Voltage") == []
