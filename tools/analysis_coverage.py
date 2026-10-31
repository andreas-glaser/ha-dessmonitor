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


def _units_by_title(analysis: dict[str, Any]) -> dict[str, str]:
    """Collect the units an analysis observed, keyed by raw title.

    ``sample_data`` holds the first twenty readings and ``parameters`` the
    queryDeviceParsEs entries, so a title may legitimately have no unit here.
    """
    units: dict[str, str] = {}
    for section, label in (("sample_data", "title"), ("parameters", "name")):
        for point in analysis.get(section, []):
            title = point.get(label)
            unit = (point.get("unit") or "").strip()
            if title and unit:
                units[str(title)] = unit
    return units


def report(path: Path) -> int:
    """Print one analysis file's sensor coverage and return the unresolved count."""
    with path.open("r", encoding="utf-8") as handle:
        analysis = json.load(handle).get("analysis", {})

    devcode = analysis.get("devcode")
    titles = analysis.get("sensor_titles", [])
    if devcode is None or not titles:
        raise ValueError(f"{path} is not a devcode analysis report")

    units = _units_by_title(analysis)
    resolved: list[tuple[str, str]] = []
    unresolved: list[str] = []
    for title in titles:
        mapped = apply_devcode_transformations(devcode, {"title": title}).get("title")
        key = resolve_sensor_key(mapped, title)
        if key:
            resolved.append((title, key))
        else:
            unresolved.append(title)

    supported = "registered" if is_devcode_supported(devcode) else "UNREGISTERED"
    print(f"{path} - devcode {devcode} ({supported})")
    print(f"  resolved {len(resolved)}/{len(titles)}")
    for title, key in resolved:
        arrow = "" if title == key else f" -> {key}"
        print(f"    {title}{arrow}")

    with_units = [title for title in unresolved if title in units]
    print(f"  unresolved {len(unresolved)}, of which {len(with_units)} carry a unit")
    for title in unresolved:
        unit = units.get(title)
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
