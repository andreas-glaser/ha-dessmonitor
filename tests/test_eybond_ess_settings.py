"""The Eybond ESS setpoint vocabulary, and the evidence for every title in it.

Devcodes 6514, 6515 and 6544 share one table of setpoints their collectors
return among the telemetry, in ``device_support/eybond_ess.py``. Three downloads
stand behind it: the ANENJI 4.2KW 24V device diagnostics for 6514, the Maxsky
EM11000 report for 6515 (#76), and three ANENJI ANJ-11KW-48V-W-P inverters on
one account for 6544 (#77).

A shared table is only honest if nothing in it is a guess, so the first test
below requires every title to arrive as a reading and be named as a control
field on at least one of those devices. The rest check the two properties that
matter to an installation: a declared setting never takes a sensor away, and
each download now reports its devcode supported.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    is_setting_reading,
)
from custom_components.dessmonitor.device_support.device_registry import (
    get_devcode_config,
)
from custom_components.dessmonitor.device_support.eybond_ess import SETTING_READINGS
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key
from custom_components.dessmonitor.support_report import (
    device_support_status,
    normalized_reports,
)

EVIDENCE = Path(__file__).resolve().parent.parent / "docs/evidence/devcodes"

FAMILY = (6514, 6515, 6544)

# The downloads, one per devcode, each the file the reporter attached.
DOWNLOADS = {
    6514: EVIDENCE / "analysis_6514_anenji_4200.json",
    6515: EVIDENCE / "analysis_6515.json",
    6544: EVIDENCE / "analysis_6544_anenji_11kw.json",
}


def _normalize(title: str) -> str:
    return " ".join(title.split()).casefold()


def _devices(devcode: int) -> list[dict[str, Any]]:
    """Return each device in a download as readings plus control-field names.

    The two shapes are the device diagnostics download, which carries a report
    per device, and the older CLI analysis, which carries titles without the
    unit of all but its first twenty samples.
    """
    payload = json.loads(DOWNLOADS[devcode].read_text("utf-8"))
    if "data" in payload:
        return [
            {
                "readings": [
                    {"title": row["title"], "val": row["value"], "unit": row["unit"]}
                    for row in device["readings"]
                ],
                "controls": [field["name"] for field in device["control_fields"]],
            }
            for device in payload["data"]["devices"]
        ]
    analysis = payload["analysis"]
    units = {
        sample["title"]: sample.get("unit", "") for sample in analysis["sample_data"]
    }
    return [
        {
            "readings": [
                {"title": title, "val": "", "unit": units.get(title, "")}
                for title in analysis["sensor_titles"]
            ],
            "controls": [field["name"] for field in analysis["control_fields"]],
        }
    ]


def _resolved_key(devcode: int, title: str) -> str | None:
    mapped = apply_devcode_transformations(devcode, {"title": title}).get("title")
    return resolve_sensor_key(mapped, title)


@pytest.mark.parametrize("devcode", FAMILY)
def test_each_profile_shares_the_one_table(devcode: int) -> None:
    """One table, not three copies of it: identity, not equality."""
    assert get_devcode_config(devcode)["setting_readings"] is SETTING_READINGS


def test_every_declared_setting_is_a_control_on_a_measured_device() -> None:
    """No title in the shared table is a guess.

    Each must arrive among the readings of one of the three downloads and be
    spelled as a control field of that same device, so the value it carries
    already reaches Home Assistant through that control rather than being
    hidden by the declaration.
    """
    evidenced: set[str] = set()
    for devcode in FAMILY:
        for device in _devices(devcode):
            titles = {_normalize(row["title"]) for row in device["readings"]}
            controls = {_normalize(name) for name in device["controls"]}
            evidenced |= titles & controls

    missing = sorted(
        setting
        for setting in SETTING_READINGS
        if _normalize(setting) not in evidenced
    )
    assert missing == []


@pytest.mark.parametrize("devcode", FAMILY)
def test_no_reading_that_reaches_a_sensor_is_declared_a_setting(devcode: int) -> None:
    """A declaration must never take a live sensor away."""
    for device in _devices(devcode):
        for row in device["readings"]:
            if _resolved_key(devcode, row["title"]) is not None:
                assert not is_setting_reading(devcode, row["title"]), row["title"]


@pytest.mark.parametrize("devcode", FAMILY)
def test_every_setpoint_the_device_reports_is_declared(devcode: int) -> None:
    """A reading that is also a control on the same device is a setting.

    This is the check the unit cannot make: the CLI analysis behind 6515
    records a unit for its first twenty samples only, so a status built from it
    would call the devcode supported however many setpoints were left
    undeclared (#76).
    """
    for device in _devices(devcode):
        controls = {_normalize(name) for name in device["controls"]}
        setpoints = [
            row["title"]
            for row in device["readings"]
            if _normalize(row["title"]) in controls
            and _resolved_key(devcode, row["title"]) is None
        ]
        assert setpoints
        for title in setpoints:
            assert is_setting_reading(devcode, title), title


@pytest.mark.parametrize("devcode", FAMILY)
def test_every_setpoint_the_download_reported_missing_is_declared(
    devcode: int,
) -> None:
    """The readings each owner was told were missing were all settings.

    Only the two hardware identity fields are left, and they carry no unit, so
    the support report calls the devcode supported and the Repairs card goes.
    """
    for device in _devices(devcode):
        support = device_support_status(devcode, device["readings"])
        assert support["status"] == "supported"
        assert support["unresolved_with_unit"] == []
        assert [
            title
            for title in support["unresolved_without_unit"]
            if title not in ("Equipment type", "Protocol Number")
        ] == []


@pytest.mark.parametrize("devcode", FAMILY)
def test_declaring_settings_changes_no_sensor_entity(hass, devcode: int) -> None:
    """The same sensors, with the same unique ids, before and after."""

    def unique_ids(readings: list[dict[str, Any]]) -> set[str]:
        coordinator = MagicMock(
            hass=hass,
            data={
                "TEST-SN": {
                    "collector": {"pn": "TEST-PN"},
                    "device": {"devcode": devcode, "alias": "Home"},
                    "data": readings,
                }
            },
        )
        return {
            entity.unique_id for entity in _build_sensor_entities(coordinator, set())
        }

    config = get_devcode_config(devcode)
    for device in _devices(devcode):
        with_settings = unique_ids(device["readings"])
        with patch.dict(config, {"setting_readings": set()}):
            without_settings = unique_ids(device["readings"])

        assert with_settings == without_settings
        assert len(with_settings) == len({uid.casefold() for uid in with_settings})


def test_the_6544_evidence_is_the_download_it_claims_to_be() -> None:
    """Three inverters on one account, each report unmodified (#77)."""
    records = normalized_reports(json.loads(DOWNLOADS[6544].read_text("utf-8")))

    assert len(records) == 3
    for record in records:
        assert record["devcode"] == 6544
        assert record["checksum_valid"] is True
