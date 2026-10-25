"""The changelog guard that keeps released sections closed."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

RELEASED = """# Changelog

## [Unreleased]

## [1.1.0] - 2026-01-02

Prose about the release is not an entry.

### Added
- One new thing.
  Continuation lines are part of the same entry.

### Fixed
- One fix.
- Another fix.
"""


def _module() -> ModuleType:
    path = Path(__file__).parents[1] / "tools" / "check_changelog.py"
    spec = importlib.util.spec_from_file_location("check_changelog", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_counts_entries_and_ignores_unreleased() -> None:
    sections = _module().parse(RELEASED)

    # Prose is not an entry, so the section body holds no count of its own.
    assert sections == {"1.1.0": {"Added": 1, "Fixed": 2}}


def test_rewording_a_released_entry_is_allowed() -> None:
    check = _module()
    reworded = RELEASED.replace("- One fix.", "- One fix, described more honestly.")

    assert check.differences(
        "1.1.0", check.parse(RELEASED)["1.1.0"], check.parse(reworded)["1.1.0"]
    ) == []


def test_entries_merged_into_a_released_section_are_reported() -> None:
    """The failure this guard exists for: a dev merge lands under a shipped tag."""
    check = _module()
    merged = RELEASED.replace(
        "- Another fix.\n",
        "- Another fix.\n- Work that landed after 1.1.0 shipped.\n\n### Changed\n- A behaviour change.\n",
    )

    problems = check.differences(
        "1.1.0", check.parse(RELEASED)["1.1.0"], check.parse(merged)["1.1.0"]
    )

    assert problems == [
        "  ### Changed: not in v1.1.0, now has 1 entry",
        "  ### Fixed: 2 entries in v1.1.0, now 3 entries",
    ]


def test_removing_a_released_entry_is_reported() -> None:
    check = _module()
    trimmed = RELEASED.replace("### Added\n- One new thing.\n", "")

    problems = check.differences(
        "1.1.0", check.parse(RELEASED)["1.1.0"], check.parse(trimmed)["1.1.0"]
    )

    assert problems == ["  ### Added: had 1 entry in v1.1.0, now absent"]
