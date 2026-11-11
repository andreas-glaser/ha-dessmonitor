"""Value mappings for devcode 6514, from the redacted analysis in #35.

The profile shipped for battery SOC only, so its priority and mode sensors
reported raw API codes. Each expectation below comes from the committed
analysis: the observed telemetry values and the collector's own control enums
bse_eybond_read_55 and bat_eybond_read_74.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    is_setting_reading,
)
from custom_components.dessmonitor.device_support.device_registry import (
    get_devcode_config,
    map_control_field,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key
from custom_components.dessmonitor.support_report import (
    device_support_status,
    normalized_reports,
)


@pytest.mark.parametrize(
    "title,raw,expected",
    [
        ("Output Priority", "SBU", "Solar → Battery → Utility"),
        ("Output Priority", "SUB", "Solar → Utility → Battery"),
        ("Output Priority", "UTI", "Utility First"),
        ("Output Priority", "SOL", "Solar First"),
        ("Output Priority", "SUF", "Solar → Utility First"),
        ("Charger Source Priority", "OSO", "Only Solar"),
        ("Charger Source Priority", "SNU", "Solar and Utility"),
        # The reporter's manual settles CSO as solar-first charging (#56).
        ("Charger Source Priority", "CSO", "Solar First"),
        # A code no evidence covers is still shown as the collector sent it.
        ("Charger Source Priority", "XYZ", "XYZ"),
        ("Operating mode", "OffgridMode", "Off-grid Mode"),
        ("Operating mode", "Unrecognized mode", "Unrecognized mode"),
    ],
)
def test_observed_values_are_labelled(title: str, raw: str, expected: str) -> None:
    point = {"title": title, "val": raw, "unit": ""}
    assert apply_devcode_transformations(6514, point)["val"] == expected
    assert point["val"] == raw


@pytest.mark.parametrize(
    "title,raw,expected",
    [
        ("Output Priority", "SBU", "Solar → Battery → Utility"),
        ("Charger Source Priority", "OSO", "Only Solar"),
        ("Charger Source Priority", "CSO", "Solar First"),
        ("Operating mode", "OffgridMode", "Off-grid Mode"),
    ],
)
def test_mapped_value_is_a_valid_enum_state(
    hass, title: str, raw: str, expected: str
) -> None:
    """A label the integration shows must be in the entity's option list."""
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": 6514, "alias": "Home"},
                "data": [{"title": title, "val": raw, "unit": ""}],
            }
        },
    )

    (sensor,) = _build_sensor_entities(coordinator, set())

    assert sensor.native_value == expected
    assert sensor.native_value in sensor.options


# ---------------------------------------------------------------------------
# Setpoints declared as settings, from the ANENJI 4.2KW 24V diagnostics
# download. Its support report counted twenty readings with a unit as missing;
# every one was the value of a control the same device publishes.
# ---------------------------------------------------------------------------

EVIDENCE = (
    Path(__file__).resolve().parent.parent
    / "docs/evidence/devcodes/analysis_6514_anenji_4200.json"
)


def _evidence_device() -> dict[str, Any]:
    with EVIDENCE.open(encoding="utf-8") as handle:
        (device,) = json.load(handle)["data"]["devices"]
    return device


def _evidence_points() -> list[dict[str, Any]]:
    """Return the download's readings as the coordinator holds them."""
    return [
        {"title": row["title"], "val": row["value"], "unit": row["unit"]}
        for row in _evidence_device()["readings"]
    ]


def _declared_settings() -> set[str]:
    return set(get_devcode_config(6514)["setting_readings"])


def _declared_settings_this_device_reports() -> set[str]:
    """The declarations the evidence below can speak for.

    The table is the Eybond ESS family's, shared with devcodes 6515 and 6544,
    so it names settings this collector does not send - the scheduled secondary
    priorities, the clock - and a download cannot justify those. The family
    guard in ``tests/test_eybond_ess_settings.py`` requires every title to be a
    reading and a control on at least one committed download; here the question
    is only whether this device's own are.
    """
    reported = {_normalize(row["title"]) for row in _evidence_device()["readings"]}
    return {
        setting
        for setting in _declared_settings()
        if _normalize(setting) in reported
    }


def _normalize(title: str) -> str:
    return " ".join(title.split()).casefold()


def _resolved_key(title: str) -> str | None:
    mapped = apply_devcode_transformations(6514, {"title": title}).get("title")
    return resolve_sensor_key(mapped, title)


def test_the_evidence_is_the_download_it_claims_to_be() -> None:
    (record,) = normalized_reports(json.loads(EVIDENCE.read_text("utf-8")))
    assert record["devcode"] == 6514
    assert record["checksum_valid"] is True


def test_every_reading_reported_missing_was_a_declared_setting() -> None:
    """The twenty titles behind "missing 20 readings" are all settings now."""
    reported = _evidence_device()["support"]["unresolved_with_unit"]
    assert len(reported) == 20
    for item in reported:
        assert is_setting_reading(6514, item["title"]), item["title"]
        assert _resolved_key(item["title"]) is None


def test_every_declared_setting_is_a_control_on_the_same_device() -> None:
    """A declaration is justified by the control template, never guessed.

    Each title must arrive among the readings and be spelled as a control field
    of the same device, so the value it carries already reaches Home Assistant
    through that control rather than being hidden.
    """
    device = _evidence_device()
    controls = {_normalize(field["name"]) for field in device["control_fields"]}
    settings = _declared_settings_this_device_reports()
    assert len(settings) == 36
    for setting in settings:
        assert _normalize(setting) in controls, setting


def test_the_padded_vendor_title_is_matched() -> None:
    assert is_setting_reading(6514, "SOC Protection value of OP1  In off-grid mode")


@pytest.mark.parametrize("title", ["Equipment type", "Protocol Number"])
def test_hardware_identity_fields_are_not_declared_settings(title: str) -> None:
    assert is_setting_reading(6514, title) is False


def test_no_reading_that_reaches_a_sensor_is_declared_a_setting() -> None:
    """A declaration must never take a live sensor away, Output Voltage
    Setting and Output frequency included."""
    for point in _evidence_points():
        if _resolved_key(point["title"]) is not None:
            assert not is_setting_reading(6514, point["title"]), point["title"]


def test_the_download_now_reports_the_devcode_supported() -> None:
    support = device_support_status(6514, _evidence_points())

    assert support["status"] == "supported"
    assert support["unresolved_with_unit"] == []
    # Only the two identity fields stay unresolved; they carry no unit.
    assert support["unresolved_without_unit"] == ["Equipment type", "Protocol Number"]
    assert support["excluded"]["declared_settings"] == len(
        _declared_settings_this_device_reports()
    )
    assert support["resolved"] == 38
    assert support["resolved"] + support["unresolved"] == support["total"]


def test_declaring_settings_changes_no_sensor_entity(hass) -> None:
    """The same sensors, with the same unique ids, before and after."""

    def unique_ids() -> set[str]:
        coordinator = MagicMock(
            hass=hass,
            data={
                "TEST-SN": {
                    "collector": {"pn": "TEST-PN"},
                    "device": {"devcode": 6514, "alias": "Home"},
                    "data": _evidence_points(),
                }
            },
        )
        return {
            entity.unique_id for entity in _build_sensor_entities(coordinator, set())
        }

    with_settings = unique_ids()
    config = get_devcode_config(6514)
    with patch.dict(config, {"setting_readings": set()}):
        without_settings = unique_ids()

    assert with_settings == without_settings
    assert len(with_settings) == len({uid.casefold() for uid in with_settings})
    for setting in _declared_settings():
        slug = _normalize(setting).replace(" ", "_")
        assert f"TEST-SN_{slug}" not in with_settings


def test_control_names_and_unique_ids_are_untouched() -> None:
    """Declaring settings must not rename, add or reclassify a control."""
    config = get_devcode_config(6514)
    assert "control_field_mappings" not in config
    assert "temporal_controls" not in config
    for field in _evidence_device()["control_fields"]:
        name = " ".join(field["name"].split())
        assert map_control_field(6514, field["name"]) == name


@pytest.mark.parametrize("devcode", [2477, 518])
def test_a_profile_outside_the_family_does_not_inherit_the_declarations(
    devcode: int,
) -> None:
    """Only a profile that imports the table gets it.

    Devcodes 6515 and 6544 do import it, each on its own download (#76, #77),
    and are checked in ``tests/test_eybond_ess_settings.py``. A Voltronic PI30
    collector spells its setpoints differently and must not be given these.
    """
    for title in ("Maximum charging voltage", "Eq charging voltage", "Remote switch"):
        assert is_setting_reading(devcode, title) is False


def test_a_partial_cloud_response_stays_supported() -> None:
    """Readings dropped from a refresh must not raise or flip the status."""
    points = _evidence_points()
    for subset in (points[::2], points[1::2], points[:5], []):
        support = device_support_status(6514, subset)
        assert support["status"] == "supported"
        assert support["unresolved_with_unit"] == []


def test_an_unknown_reading_with_a_unit_is_still_caught() -> None:
    """The declarations close this gap without blinding the guard."""
    points = _evidence_points() + [
        {"title": "Battery cycle count", "val": "12", "unit": "Times"}
    ]
    support = device_support_status(6514, points)
    assert support["status"] == "partial"
    assert [item["title"] for item in support["unresolved_with_unit"]] == [
        "Battery cycle count"
    ]


async def test_the_repairs_card_is_withdrawn_for_the_download(hass) -> None:
    from homeassistant.helpers import issue_registry as ir

    from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
    from custom_components.dessmonitor.const import DOMAIN

    coordinator = DessMonitorDataUpdateCoordinator(hass, AsyncMock(), 300)
    coordinator.config_entry = MagicMock(entry_id="entry-1")
    # The card 2.7.0 raised for this device is still registered.
    ir.async_create_issue(
        hass,
        DOMAIN,
        "devcode_support_6514",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="devcode_partial",
    )

    coordinator._async_update_support_issues(
        {
            "SN-1": {
                "collector": {"pn": "PN-1"},
                "device": {"devcode": 6514, "devaddr": 1, "alias": "Home"},
                "data": _evidence_points(),
            }
        }
    )

    assert ir.async_get(hass).async_get_issue(DOMAIN, "devcode_support_6514") is None
