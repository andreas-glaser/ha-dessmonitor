"""Devcode 518 title mapping, against a sanitized API response.

Without this mapping the energy and power sensors of a grid-tie PV inverter sit
at 0 while the data is present in the payload, because devcode 518 reports
lower-cased, spelled-out titles that do not match the canonical sensor names.
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.device_support.device_registry import (
    get_device_model_name,
    map_sensor_title,
)

FIXTURE = Path(__file__).parent / "fixtures" / "devcode_518_query_device_last_data.json"
DEVCODE = 518


def _titles() -> list[str]:
    with FIXTURE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["dat"]["devcode"] == DEVCODE
    return [entry["title"] for entry in payload["dat"]["title"]]


def test_fixture_carries_no_account_identifiers() -> None:
    """The fixture must stay safe to ship in the repository."""
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "REDACTED" in raw
    for leaky in ("token", "sign=", "salt=", "secret"):
        assert leaky not in raw


def test_the_device_is_recognised() -> None:
    assert "518" in get_device_model_name(DEVCODE)


def test_energy_and_power_titles_map_to_canonical_names() -> None:
    """These four are the ones that used to read 0."""
    assert map_sensor_title(DEVCODE, "active power") == "Output Active Power"
    assert map_sensor_title(DEVCODE, "DC output power") == "PV Power"
    assert map_sensor_title(DEVCODE, "total energy") == "Energy Total"
    assert map_sensor_title(DEVCODE, "today energy") == "Energy Today"


def test_every_mapped_title_resolves_to_a_known_sensor() -> None:
    """A mapping that points at a name the integration does not know is dead."""
    for title in _titles():
        mapped = map_sensor_title(DEVCODE, title)
        if mapped != title:
            assert mapped in SENSOR_TYPES, f"{title!r} maps to unknown {mapped!r}"


def test_unmapped_titles_pass_through_unchanged() -> None:
    """ "grid voltage" is already canonical, so it must not be rewritten."""
    assert map_sensor_title(DEVCODE, "grid voltage") == "grid voltage"


def test_other_devcodes_are_untouched_by_this_mapping() -> None:
    """The 518 table must not leak into devices that report the same titles."""
    assert map_sensor_title(2376, "active power") == "active power"
