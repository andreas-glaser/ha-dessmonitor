"""The inventory a release is compared against.

The test suite says the code is consistent. It does not say that an existing
installation still publishes what it published, and over 13,000 of them run
this integration and none can be tested from here. The inventory is how that
question gets an answer: build every sensor for every device under
``docs/evidence/`` on two checkouts and diff the lines.

It is run here the way a maintainer runs it, as its own process against a
checkout, because that is the only way its import of the integration behaves
as it does on the command line.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TOOL = _ROOT / "tools" / "entity_inventory.py"

_RESULT = subprocess.run(
    [sys.executable, str(_TOOL), str(_ROOT)],
    capture_output=True,
    text=True,
    timeout=300,
    check=False,
    cwd=_ROOT,
)
_LINES = [
    line for line in _RESULT.stdout.splitlines() if line and not line.startswith("#")
]
_FIELDS = 8


def test_the_tool_runs_against_a_checkout() -> None:
    """A maintainer runs this before a release; it has to work on its own."""
    assert _RESULT.returncode == 0, _RESULT.stderr
    assert _RESULT.stdout.startswith("# evidence|devcode|unique_id|")
    assert _LINES, "no entities were built from the committed evidence"


def test_the_inventory_describes_every_sensor_once() -> None:
    """One line per entity, in a stable order, or a diff is unreadable."""
    assert len(_LINES) == len(set(_LINES))
    assert all(len(line.split("|")) == _FIELDS for line in _LINES)
    assert _LINES == sorted(_LINES)


def test_the_inventory_names_the_facts_a_release_must_not_change() -> None:
    """A unit, a device class or a category moving is the thing it catches."""
    rows = [line.split("|") for line in _LINES]
    by_id = {(row[1], row[2]): row for row in rows if row[0] == "analysis_6515.json"}

    battery = by_id[("6515", "SN_battery_voltage")]
    assert battery[3] == "Home Battery Voltage"
    assert battery[4] == "V"
    assert battery[5] == "voltage"
    assert battery[6] == "measurement"

    # The freshness sensor is additive, and this is the line that says so.
    assert ("6515", "SN_last_reading_received") in by_id
