"""Devcode 2500 on a MUST PH18 5.5KW, which arrived with no profile (#91).

Twenty-three of its twenty-five readings already resolved through the generic
fallback, because this collector speaks the same vocabulary devcode 697 does.
Two did not, and both carry a unit, which is what held the Repairs card open.

Every title and value asserted here comes from
``docs/evidence/devcodes/analysis_2500.json``, which is the reporter's own
diagnostics download.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.device_support.device_registry import (
    is_devcode_supported,
)
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key
from custom_components.dessmonitor.support_report import resolved_key_for

DEVCODE = 2500

EVIDENCE = (
    Path(__file__).resolve().parent.parent
    / "docs/evidence/devcodes/analysis_2500.json"
)

# The two readings that reached no entity, and the key each now reaches.
ADDED = {
    "Accumulated PV Power": "PV Cumulative Power Generation",
    "accumulated PV_sell power": "Accumulated PV Sell Power",
}

# The record's own identity. Neither carries a unit, so neither holds the
# Repairs card open, and the integration publishes both as attributes.
ATTRIBUTE_TITLES = {"id", "Timestamp"}


def _device() -> dict[str, Any]:
    payload = json.loads(EVIDENCE.read_text("utf-8"))
    devices = payload["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["devcode"] == DEVCODE
    return devices[0]


def _key(title: str) -> str | None:
    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reading_that_carries_a_unit_reaches_a_sensor() -> None:
    """The whole point of the profile: no unit-carrying reading is dropped."""
    unresolved = [
        reading["title"]
        for reading in _device()["readings"]
        if reading.get("unit") and not _key(reading["title"])
    ]

    assert unresolved == []


def test_every_reading_in_the_download_is_accounted_for() -> None:
    titles = {reading["title"] for reading in _device()["readings"]}
    unresolved = {title for title in titles if not _key(title)}

    assert unresolved == ATTRIBUTE_TITLES


def test_the_two_added_readings_reach_the_keys_this_profile_names() -> None:
    for title, expected in ADDED.items():
        assert _key(title) == expected, title


def test_the_lifetime_array_counter_shares_devcode_697s_key() -> None:
    """Same title, same vocabulary, same sensor - not a second spelling.

    Devcode 697 maps "Accumulated PV Power" to this key from its own
    download. A new key for the same title would publish the same
    measurement under two names across the family.
    """
    assert _key("Accumulated PV Power") == resolved_key_for(
        697, {"title": "Accumulated PV Power", "val": "1"}
    )


def test_the_pv_sell_counter_is_not_mapped_onto_the_counter_beside_it() -> None:
    """Both read 58 kWh in the download and they stay two sensors.

    A system that exports only solar reports the same figure on both whether
    or not they are one register, so the equal figure is not evidence. The
    mapping that would collapse them is the one that could later publish
    whichever the merge preferred, in silence.
    """
    readings = {
        reading["title"]: reading["value"] for reading in _device()["readings"]
    }
    assert readings["accumulated PV_sell power"] == "58"
    assert readings["Accumulated Sell Power"] == "58"

    assert _key("accumulated PV_sell power") != _key("Accumulated Sell Power")


def test_the_new_key_publishes_an_energy_counter() -> None:
    sensor = SENSOR_TYPES["Accumulated PV Sell Power"]

    assert sensor["unit"] == "kWh"
    assert sensor["device_class"] == "energy"
    assert sensor["state_class"] == "total_increasing"


def test_the_new_key_claims_no_other_devcodes_title() -> None:
    """A new key reaches every devcode whose raw title normalises to it.

    Title resolution ignores case and whitespace, so naming a key after a
    string some other collector already sends starts publishing a reading
    that devcode may have been dropping on purpose (#58). No committed title
    normalises to this one, so devcode 2500 reaches it only through its own
    profile mapping and no other installation is touched.
    """
    senders = set()
    for path in sorted(EVIDENCE.parent.glob("analysis_*.json")):
        payload = json.loads(path.read_text("utf-8"))
        # A CLI analysis and a diagnostics download are both committed here,
        # and only the download nests its devices under "data".
        devices = payload.get("data", payload).get("devices") or []
        for device in devices:
            for reading in device.get("readings", []):
                if resolve_sensor_key(reading["title"]) == "Accumulated PV Sell Power":
                    senders.add((device.get("devcode"), reading["title"]))

    assert senders == set()


def test_the_work_state_title_is_left_where_it_is() -> None:
    """Mapping it onto "Operating mode" would change a unique id on every
    installation already running this devcode through the fallback."""
    assert _key("work state") == "work state"


def test_no_control_field_is_repeated_as_a_reading() -> None:
    """Which is why this profile declares no settings (#53, #61)."""
    titles = {
        " ".join(reading["title"].split()).casefold()
        for reading in _device()["readings"]
    }
    controls = {
        " ".join(control["name"].split()).casefold()
        for control in _device()["control_fields"]
    }

    assert titles & controls == set()
