#!/usr/bin/env python3
"""Verify that released CHANGELOG sections still match the tags that shipped them.

Entries accumulate under ``## [Unreleased]`` on ``dev``. Preparing a release
inserts the new version heading above those entries, which leaves the lines that
``dev`` keeps appending to inside the published section. A later merge from
``dev`` then files new entries under a tag that never shipped them, and git
reports no conflict because both sides edited different lines.

This check reads every released section back from its own tag and fails when the
entries no longer line up, so a mis-filed merge cannot reach a release.

Usage:
    python3 tools/check_changelog.py [--require-version X.Y.Z]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

CHANGELOG = "CHANGELOG.md"
_SECTION = re.compile(r"^## \[([^\]]+)\]")
_SUBSECTION = re.compile(r"^### (.+?)\s*$")

# Entry counts per subsection, keyed by version: {"2.6.0-rc.1": {"Fixed": 5}}
Sections = dict[str, dict[str, int]]


def parse(text: str) -> Sections:
    """Count the top-level entries in each subsection of each released section."""
    sections: Sections = {}
    current: dict[str, int] | None = None
    subsection = ""
    for line in text.splitlines():
        if match := _SECTION.match(line):
            version = match.group(1)
            if version == "Unreleased":
                current = None
                continue
            current = sections.setdefault(version, {})
            subsection = ""
        elif current is not None and (match := _SUBSECTION.match(line)):
            subsection = match.group(1)
            current.setdefault(subsection, 0)
        elif current is not None and line.startswith("- "):
            current[subsection] = current.get(subsection, 0) + 1
    return sections


def tagged_changelog(version: str) -> str | None:
    """Read CHANGELOG.md as of ``v<version>``, or None when that tag is absent."""
    tag = f"v{version}"
    if subprocess.run(
        ["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
        capture_output=True,
    ).returncode:
        return None
    result = subprocess.run(
        ["git", "show", f"{tag}:{CHANGELOG}"],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def _entries(count: int) -> str:
    return f"{count} entry" if count == 1 else f"{count} entries"


def differences(
    version: str, released: dict[str, int], now: dict[str, int]
) -> list[str]:
    """Describe how a section's entry counts drifted from what its tag shipped."""
    problems = []
    for subsection in sorted(set(released) | set(now)):
        was = released.get(subsection)
        is_now = now.get(subsection)
        if was == is_now:
            continue
        label = f"### {subsection}" if subsection else "section body"
        if was is None:
            problems.append(
                f"  {label}: not in v{version}, now has {_entries(now[subsection])}"
            )
        elif is_now is None:
            problems.append(f"  {label}: had {_entries(was)} in v{version}, now absent")
        else:
            problems.append(
                f"  {label}: {_entries(was)} in v{version}, now {_entries(is_now)}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-version",
        metavar="X.Y.Z",
        help="also fail unless a section for this version exists",
    )
    args = parser.parse_args()

    path = Path(CHANGELOG)
    if not path.is_file():
        print(f"{CHANGELOG} not found; run this from the repository root")
        return 2
    current = parse(path.read_text(encoding="utf-8"))

    if args.require_version and args.require_version not in current:
        print(f"No changelog section found for version {args.require_version}")
        return 1

    failures: list[str] = []
    checked = 0
    for version, now in current.items():
        text = tagged_changelog(version)
        if text is None:
            continue
        checked += 1
        released = parse(text).get(version)
        if released is None:
            failures.append(
                f"v{version} is tagged but its own section is missing from "
                f"{CHANGELOG} at that tag"
            )
            continue
        if problems := differences(version, released, now):
            failures.append(
                f"Section [{version}] no longer matches what v{version} shipped:\n"
                + "\n".join(problems)
            )

    if failures:
        print("\n\n".join(failures))
        print(
            "\nA released section is closed. Entries for new work belong under "
            "[Unreleased], or under the section of the release being prepared."
        )
        return 1

    if not checked:
        print(
            f"No released sections could be compared: no matching tags are "
            f"available. Fetch tags to check {CHANGELOG} history."
        )
        return 0

    print(f"{checked} released changelog section(s) match their tags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
