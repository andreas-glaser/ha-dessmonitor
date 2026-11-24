#!/usr/bin/env python3
"""Print every sensor entity the integration would publish for the committed
evidence, so two checkouts can be compared line by line.

Over 13,000 installations run this integration and none of them can be tested
from here, so the question before a release is not "do the tests pass" but
"does an existing install still publish what it published". This answers it the
only way available: build the entities for every device under
``docs/evidence/`` and diff the result against the last tag.

    git worktree add /tmp/last v3.0.0
    .venv/bin/python tools/entity_inventory.py /tmp/last > /tmp/last.txt
    .venv/bin/python tools/entity_inventory.py . > /tmp/now.txt
    diff /tmp/last.txt /tmp/now.txt

One line per entity: evidence file, devcode, unique id, name, unit, device
class, state class, entity category. An added line is a new sensor. A removed
or changed line is an entity that moved, and that needs its own CHANGELOG entry
and an upgrade note rather than riding along with other work.

This covers the sensor platform, which is where nearly all of them are. The
control platforms build from a live control template rather than from a
payload, so they are not reachable this way and still need a reporter.

Two things it deliberately does not do, each of which cost a run when the
comparison was done by hand:

* It does not print the readings' values, and every data point is given the
  same placeholder. Each checkout runs its own copy of the normaliser that
  reads the evidence files, and an older one answers differently about values,
  which made 521 entities look changed when none had. What must not move is an
  entity's identity and metadata, and that is what the line carries.
* It reads each checkout's own ``docs/evidence/``. A devcode whose evidence
  file is new on the branch therefore shows up as added lines under a file
  name the other side does not have, which is a new devcode rather than a
  moved entity.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

FIELDS = (
    "evidence",
    "devcode",
    "unique_id",
    "name",
    "unit",
    "device_class",
    "state_class",
    "entity_category",
)


def inventory(root: Path) -> list[str]:
    """Return one sorted line per entity this checkout would publish."""
    sys.path.insert(0, str(root))
    from custom_components.dessmonitor.sensor import _build_sensor_entities
    from custom_components.dessmonitor.support_report import normalized_reports

    rows: set[str] = set()
    for path in sorted(root.joinpath("docs/evidence").rglob("analysis_*.json")):
        with path.open(encoding="utf-8") as handle:
            records = normalized_reports(json.load(handle))
        for record in records:
            devcode = record["devcode"]
            points = [
                {"title": title, "val": "1", "unit": unit}
                for title, unit in sorted(dict(record["units"]).items())
            ]
            known = {point["title"] for point in points}
            points.extend(
                {"title": title, "val": "1", "unit": ""}
                for title in sorted(record.get("titles") or [])
                if title not in known
            )
            coordinator = MagicMock(
                data={
                    "SN": {
                        "collector": {"pn": "PN"},
                        "device": {
                            "devcode": devcode,
                            "alias": "Home",
                            "devaddr": 1,
                        },
                        "data": points,
                    }
                }
            )
            for entity in _build_sensor_entities(coordinator, set()):
                rows.add(
                    "|".join(
                        str(value)
                        for value in (
                            path.name,
                            devcode,
                            entity.unique_id,
                            entity.name,
                            entity.native_unit_of_measurement,
                            getattr(entity, "device_class", None),
                            getattr(entity, "state_class", None),
                            getattr(entity, "entity_category", None),
                        )
                    )
                )
    return sorted(rows)


def main() -> int:
    """Print the inventory for the checkout named on the command line."""
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.joinpath("custom_components/dessmonitor").is_dir():
        print(f"{root} is not a checkout of this integration", file=sys.stderr)
        return 2
    print("# " + "|".join(FIELDS))
    print("\n".join(inventory(root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
