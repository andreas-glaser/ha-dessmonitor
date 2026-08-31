"""Frontend translation coverage for config and options flows."""

from __future__ import annotations

import json
from pathlib import Path


def test_english_frontend_translations_match_canonical_strings() -> None:
    """Custom integrations need translations/en.json to avoid raw field keys."""
    integration = (
        Path(__file__).parents[1] / "custom_components" / "dessmonitor"
    )
    with (integration / "strings.json").open(encoding="utf-8") as source:
        canonical = json.load(source)
    with (integration / "translations" / "en.json").open(
        encoding="utf-8"
    ) as translated:
        english = json.load(translated)

    assert english == canonical
