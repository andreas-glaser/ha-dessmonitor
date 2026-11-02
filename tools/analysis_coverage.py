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
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.dessmonitor.device_support import (  # noqa: E402
    apply_devcode_transformations,
    is_devcode_supported,
)
from custom_components.dessmonitor.sensor_titles import (  # noqa: E402
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

    @property
    def total(self) -> int:
        return len(self.resolved) + len(self.unresolved)

    @property
    def unmapped_readings(self) -> list[tuple[str, str]]:
        """Unresolved titles the collector labelled with a unit.

        A title without a unit is a setting, an identity field or a timestamp,
        which reaches Home Assistant through another platform or not at all.
        One with a unit is a reading that is being dropped.
        """
        return [
            (title, self.units[title])
            for title in self.unresolved
            if title in self.units
        ]


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
    )


def report(path: Path) -> int:
    """Print one analysis file's sensor coverage and return the unmapped count."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    try:
        records = normalized_reports(payload)
    except ValueError as err:
        raise ValueError(f"{path} is {err}") from err

    unmapped = 0
    for index, record in enumerate(records):
        unmapped += _report_one(path, record, index=index, of=len(records))
    return unmapped


def _report_one(
    path: Path, record: dict[str, Any], *, index: int = 0, of: int = 1
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
    print(
        f"  unresolved {len(result.unresolved)}, "
        f"of which {len(with_units)} carry a unit"
    )
    for title in result.unresolved:
        unit = result.units.get(title)
        print(f"    {title}{f'  [{unit}]' if unit else ''}")

    return len(with_units)


def main() -> int:
    """Report coverage for each analysis file given on the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="Analysis JSON files")
    args = parser.parse_args()

    unmapped = 0
    for path in args.files:
        unmapped += report(path)
        print()

    if unmapped:
        print(f"{unmapped} unresolved title(s) carry a unit and probably need mapping")
    return 1 if unmapped else 0


if __name__ == "__main__":
    sys.exit(main())
