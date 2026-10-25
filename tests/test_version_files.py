"""The packaged version must agree across every file that states it."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).parents[1]
INTEGRATION = REPO / "custom_components" / "dessmonitor"
# Stable SemVer, or this repository's release-candidate format.
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-rc\.[1-9]\d*)$|^\d+\.\d+\.\d+$")


def _declared_version() -> str:
    return (REPO / "VERSION").read_text(encoding="utf-8").strip()


def test_version_files_agree() -> None:
    """A release ships one version; three files have to be bumped together."""
    version = _declared_version()
    manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
    constant = re.search(
        r'^VERSION: Final = "([^"]+)"$',
        (INTEGRATION / "const.py").read_text(encoding="utf-8"),
        re.MULTILINE,
    )

    assert constant is not None, "const.py has no VERSION constant to compare"
    assert manifest["version"] == version
    assert constant.group(1) == version


def test_declared_version_is_releasable() -> None:
    """The release workflow rejects anything but x.y.z or x.y.z-rc.N."""
    assert VERSION_PATTERN.match(_declared_version())


def test_declared_version_has_a_changelog_section() -> None:
    """Whatever VERSION says is packaged must be described in the changelog."""
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{_declared_version()}]" in changelog
