"""Frontend translation coverage for config and options flows."""

from __future__ import annotations

import json
from pathlib import Path


def test_english_frontend_translations_match_canonical_strings() -> None:
    """Custom integrations need translations/en.json to avoid raw field keys."""
    integration = Path(__file__).parents[1] / "custom_components" / "dessmonitor"
    with (integration / "strings.json").open(encoding="utf-8") as source:
        canonical = json.load(source)
    with (integration / "translations" / "en.json").open(
        encoding="utf-8"
    ) as translated:
        english = json.load(translated)

    assert english == canonical


def test_both_cloud_setup_paths_explain_account_platform() -> None:
    path = Path(__file__).parents[1] / "custom_components/dessmonitor/strings.json"
    steps = json.loads(path.read_text())["config"]["step"]
    for step in ("cloud", "hybrid"):
        assert steps[step]["data"]["api_profile"] == "Account platform"
        help_text = steps[step]["data_description"]["api_profile"]
        assert "default" in help_text
        assert "SmartESS" in help_text
        assert "SmartClient for Solar" in help_text
        assert "source=" not in help_text
        assert ".com" not in help_text
