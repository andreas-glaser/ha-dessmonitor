#!/usr/bin/env python3
"""Report which raw API titles in a CLI analysis resolve to a sensor.

A devcode added for one reported symptom can leave the rest of a collector's
telemetry unmapped, because nothing in review shows which titles the resolver
still rejects. Run this against an analysis JSON before and after editing a
devcode module:

    .venv/bin/python tools/analysis_coverage.py docs/evidence/devcodes/analysis_6514.json

Titles without a unit are usually settings, identity fields or timestamps, which
reach Home Assistant as number, select or button entities rather than sensors.
Unresolved titles that do carry a unit are the ones worth mapping.

A title marked "(control on this device)" is one the same report lists in the
device's control template, so it is a setting rather than a dropped reading and
belongs in the profile's ``SETTING_READINGS``. A collector does not always spell
the two the same, though - devcode 2477 reports "Transfer To Bypass @ Overload"
as a reading against a "Transfer To Bypass Overload" control (#61) - so where a
report carries the control readbacks, an unresolved title is also printed with
any control sitting at the same value. That pairing is a candidate for the
reviewer to confirm, not a declaration: two settings can share a value and a
live reading can pass through one. Pass ``--controls`` to also list the control
fields whose names no reading title matches.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.dessmonitor.device_support import (  # noqa: E402
    apply_devcode_transformations,
    is_devcode_supported,
    is_absent_reading,
    is_setting_reading,
)
from custom_components.dessmonitor.sensor_titles import (  # noqa: E402
    normalize_sensor_title,
    resolve_sensor_key,
)
from custom_components.dessmonitor.support_report import (  # noqa: E402
    normalized_reports,
)

__all__ = ["Coverage", "coverage", "normalized_reports", "report"]


@dataclass(frozen=True)
class Coverage:
    """Which of a collector's titles reach Home Assistant as sensors.

    The contributor CLI prints a summary of this straight after an analysis, so
    a reporter sees what their own hardware is missing without waiting for a
    maintainer, and the maintainer-side report below prints the detail.
    """

    devcode: Any
    registered: bool
    resolved: list[tuple[str, str]]
    unresolved: list[str]
    units: dict[str, str]
    controls: tuple[str, ...] = ()
    values: dict[str, str] = field(default_factory=dict)
    control_values: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.resolved) + len(self.unresolved)

    @property
    def unmapped_readings(self) -> list[tuple[str, str]]:
        """Unresolved titles the collector labelled with a unit.

        A title without a unit is a setting, an identity field or a timestamp,
        which reaches Home Assistant through another platform or not at all.
        One with a unit is a reading that is being dropped - unless the profile
        declares it a setting, which is how a collector that returns its own
        setpoints among the telemetry is handled (#53), or declares that this
        hardware never fills it, which is how an idle phase on a single-phase
        inverter is handled (#58).
        """
        return [
            (title, self.units[title])
            for title in self.unresolved
            if title in self.units
            and not is_setting_reading(self.devcode, title)
            and not is_absent_reading(self.devcode, title)
        ]

    @property
    def control_names(self) -> list[str]:
        """Control-field names none of this device's reading titles matches.

        Classifying a new devcode's unresolved titles means deciding which are
        the inverter's own settings, and a diagnostics download already says:
        it carries the control template. The names are not spelled like the
        reading titles, though - devcode 2477 reports "Transfer To Bypass @
        Overload" as a reading against a "Transfer To Bypass Overload" control
        (#61) - so these are listed for the reviewer to match up rather than
        matched automatically, which would declare a real reading a setting.
        """
        reported = {
            normalize_sensor_title(title)
            for title in self.unresolved + [title for title, _ in self.resolved]
        }
        return [
            name
            for name in self.controls
            if normalize_sensor_title(name) not in reported
        ]

    def controls_reading_the_same_value(self, title: str) -> list[tuple[str, str]]:
        """Controls whose readback equals this title's value, name and value.

        This is the one judgement a new devcode needs and the one the names
        cannot answer, because a collector does not spell a reading and its
        control alike: devcode 2449 reports "Battery Re-Charge Voltage" 44.0 V
        against a "Back to Grid Voltage" control reading 44.0, and declaring
        that pair one setting is what withdrew a Repairs card naming fourteen
        missing readings (#80).

        A match is a candidate, not a conclusion. Two settings of one hardware
        can sit at the same value, and a live reading can pass through a
        setpoint's value - which is why devcode 2477's measured Output Voltage
        must stay a sensor however much it looks like its own setting. The
        reviewer confirms against the control's own name and option list.
        """
        value = self.values.get(title)
        if value is None:
            return []
        return [
            (name, readback)
            for name, readback in sorted(self.control_values.items())
            if _same_value(value, readback)
        ]

    @property
    def declared_settings(self) -> list[str]:
        """Unresolved titles the profile declares to be settings, not readings."""
        return [
            title
            for title in self.unresolved
            if is_setting_reading(self.devcode, title)
        ]

    @property
    def declared_absent(self) -> list[str]:
        """Unresolved titles the profile declares this hardware never fills."""
        return [
            title for title in self.unresolved if is_absent_reading(self.devcode, title)
        ]


def _same_value(reading: str, readback: str) -> bool:
    """Whether a reading and a control readback report the same value.

    Numeric where both parse, because the two sides are formatted differently
    - 44.0 against 44 - and textual otherwise, where "Lib" is "Lib".
    """
    try:
        return float(reading) == float(readback)
    except (TypeError, ValueError):
        return reading.strip().casefold() == readback.strip().casefold()


def coverage(record: dict[str, Any]) -> Coverage:
    """Resolve every title in one normalized record against the mappings."""
    devcode = record.get("devcode")
    titles = record.get("titles", [])
    if devcode is None or not titles:
        raise ValueError("not a devcode analysis report")

    resolved: list[tuple[str, str]] = []
    unresolved: list[str] = []
    for title in titles:
        mapped = apply_devcode_transformations(devcode, {"title": title}).get("title")
        key = resolve_sensor_key(mapped, title)
        if key:
            resolved.append((title, key))
        else:
            unresolved.append(title)

    return Coverage(
        devcode=devcode,
        registered=is_devcode_supported(devcode),
        resolved=resolved,
        unresolved=unresolved,
        units=dict(record.get("units", {})),
        controls=tuple(record.get("controls") or ()),
        values=dict(record.get("values") or {}),
        control_values=dict(record.get("control_values") or {}),
    )


def report(path: Path, *, show_controls: bool = False) -> int:
    """Print one analysis file's sensor coverage and return the unmapped count."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    try:
        records = normalized_reports(payload)
    except ValueError as err:
        raise ValueError(f"{path} is {err}") from err

    unmapped = 0
    for index, record in enumerate(records):
        unmapped += _report_one(
            path,
            record,
            index=index,
            of=len(records),
            show_controls=show_controls,
        )
    return unmapped


def _report_one(
    path: Path,
    record: dict[str, Any],
    *,
    index: int = 0,
    of: int = 1,
    show_controls: bool = False,
) -> int:
    """Print one device's coverage and return its unmapped reading count."""
    try:
        result = coverage(record)
    except ValueError as err:
        raise ValueError(f"{path} is {err}") from err

    supported = "registered" if result.registered else "UNREGISTERED"
    label = f"{path}" if of == 1 else f"{path} [device {index + 1} of {of}]"
    print(f"{label} - devcode {result.devcode} ({supported}, {record['source']})")
    print(f"  resolved {len(result.resolved)}/{result.total}")
    for title, key in result.resolved:
        arrow = "" if title == key else f" -> {key}"
        print(f"    {title}{arrow}")

    with_units = result.unmapped_readings
    settings = set(result.declared_settings)
    absent = set(result.declared_absent)
    print(
        f"  unresolved {len(result.unresolved)}, "
        f"of which {len(with_units)} carry a unit"
        + (f" and {len(settings)} are declared settings" if settings else "")
        + (f" and {len(absent)} are declared absent" if absent else "")
    )
    controls = {normalize_sensor_title(name) for name in result.controls}
    for title in result.unresolved:
        unit = result.units.get(title)
        if title in settings:
            marker = "  (setting)"
        elif title in absent:
            marker = "  (declared absent on this hardware)"
        elif normalize_sensor_title(title) in controls:
            marker = "  (control on this device)"
        else:
            marker = ""
        print(f"    {title}{f'  [{unit}]' if unit else ''}{marker}")
        if marker:
            continue
        for name, readback in result.controls_reading_the_same_value(title):
            print(
                f"        reads {readback}, as the control {name!r} does - "
                "a setting to declare if the two are one"
            )

    unmatched = result.control_names if show_controls else []
    if unmatched:
        print(
            f"  {len(unmatched)} control field(s) this device reports under a "
            "name no reading above matches; a title above may be one of them "
            "spelled differently"
        )
        for name in unmatched:
            print(f"    {name}")

    return len(with_units)


def main() -> int:
    """Report coverage for each analysis file given on the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="Analysis JSON files")
    parser.add_argument(
        "--controls",
        action="store_true",
        help=(
            "also list the control fields the device reports under a name no "
            "reading title matches, for classifying a new devcode's titles"
        ),
    )
    args = parser.parse_args()

    unmapped = 0
    for path in args.files:
        unmapped += report(path, show_controls=args.controls)
        print()

    if unmapped:
        print(f"{unmapped} unresolved title(s) carry a unit and probably need mapping")
    return 1 if unmapped else 0


if __name__ == "__main__":
    sys.exit(main())
