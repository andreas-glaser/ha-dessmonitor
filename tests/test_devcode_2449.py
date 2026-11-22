"""Devcode 2449 on a SILA MAX 7200MH, whose card said fourteen readings were
missing (#80).

None was missing. The collector returns the inverter's nameplate ratings and
its own setpoints among the telemetry, the shape devcodes 2451 (#74), 2452
(#53), 2477 (#61) and the Eybond ESS family (#69) all report. Six of the
fourteen describe the hardware and become diagnostic sensors; the other eight,
plus the battery type and AC input range that carry no unit, are the values of
controls the same device advertises.

Every title and value asserted here comes from
``docs/evidence/devcodes/analysis_2449.json``, which is the reporter's own
diagnostics download.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from custom_components.dessmonitor.device_support import is_setting_reading
from custom_components.dessmonitor.device_support.device_registry import (
    is_devcode_supported,
    local_control_options,
    local_control_setting,
)
from custom_components.dessmonitor.support_report import resolved_key_for

DEVCODE = 2449

EVIDENCE = (
    Path(__file__).resolve().parent.parent
    / "docs/evidence/devcodes/analysis_2449.json"
)

# Reading title -> the control on the same device whose value it mirrors. The
# spellings differ on both sides of six of these pairs, which is why the
# correlation is stated here rather than inferred from the names.
SETPOINT_CONTROLS = {
    "AC Input Range": "AC Input Range",
    "AC Output Rating Frequency": "Output Frequency",
    "AC Output Rating Voltage": "Output Voltage",
    "Battery Bulk Voltage": "Bulk Charging Voltage",
    "Battery Float Voltage": "Float Charging Voltage",
    "Battery Re-Charge Voltage": "Back to Grid Voltage",
    "Battery Re-Discharge Voltage": "Back to Discharge Voltage",
    "Battery Type": "Battery Type",
    "Max AC Charging Current": "Max. AC Charging Current",
    "Max Charging Current": "Max. Charging Current",
}

NAMEPLATE_RATINGS = {
    "AC Output Rating Active Power": "rated power",
    "AC Output Rating Apparent Power": "rated apparent power",
    "AC Output Rating Current": "rated current",
    "Battery Rating Voltage": "battery rated voltage",
    "Grid Rating Current": "grid rated current",
    "Grid Rating Voltage": "grid rated voltage",
}

# Identity and status fields. The download sends none of them with a unit, so
# none of them holds the Repairs card open.
IDENTITY_TITLES = {
    "Inverter Fault",
    "Machine Type",
    "Main CPU Firmware Version",
    "Model",
    "Parallel Max Num",
    "SN",
    "Secondary CPU Firmware Version",
    "Timestamp",
    "id",
}


def _device() -> dict[str, Any]:
    payload = json.loads(EVIDENCE.read_text("utf-8"))
    devices = payload["data"]["devices"]
    assert len(devices) == 1
    return devices[0]


def _key(title: str) -> str | None:
    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reading_in_the_download_is_accounted_for() -> None:
    """Each reaches a sensor, is a declared setting, or names the hardware."""
    unaccounted = [
        row["title"]
        for row in _device()["readings"]
        if _key(row["title"]) is None
        and not is_setting_reading(DEVCODE, row["title"])
        and row["title"] not in IDENTITY_TITLES
    ]

    assert unaccounted == []


def test_no_reading_carrying_a_unit_reaches_nothing() -> None:
    """The condition the Repairs card and the support status are built on."""
    missing = [
        row["title"]
        for row in _device()["readings"]
        if row.get("unit")
        and _key(row["title"]) is None
        and not is_setting_reading(DEVCODE, row["title"])
    ]

    assert missing == []


def test_the_nameplate_ratings_become_their_own_sensors() -> None:
    """A rating is a fact about the hardware, not a setting (#53)."""
    for title, key in NAMEPLATE_RATINGS.items():
        assert _key(title) == key, title


def test_no_nameplate_rating_is_also_a_control() -> None:
    """What separates the six ratings from the two spelled like ratings."""
    controls = {field["name"] for field in _device()["control_fields"]}

    assert controls.isdisjoint(NAMEPLATE_RATINGS)


def test_every_declared_setpoint_mirrors_a_control_on_this_device() -> None:
    """A declared setting is only honest if the device publishes the control.

    The values are asserted together with the names: a reading that agrees
    with the control's readback is the evidence that the two are one setting,
    and it is what separates "AC Output Rating Voltage" from a rating.
    """
    device = _device()
    readings = {row["title"]: row["value"] for row in device["readings"]}
    controls = {field["name"]: field["value"] for field in device["control_fields"]}

    for title, control in SETPOINT_CONTROLS.items():
        assert is_setting_reading(DEVCODE, title), title
        assert control in controls, control
        assert float_or_text(readings[title]) == float_or_text(controls[control]), title


def float_or_text(value: str) -> float | str:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def test_a_declared_setting_never_takes_a_sensor_away() -> None:
    """A title that resolves is a reading, whatever the vendor calls it."""
    for title in SETPOINT_CONTROLS:
        assert _key(title) is None, title


def test_no_other_devcode_inherits_these_declarations() -> None:
    """Each profile is a standalone contract (#69). Devcode 2451 declares the
    same titles from its own report and devcode 2452 spells them in lower
    case, which ``is_setting_reading`` matches; devcode 684 is a grid-tie
    profile that declares no setting at all."""
    assert not is_setting_reading(684, "Battery Bulk Voltage")
    assert not is_setting_reading(684, "Max Charging Current")


# The second committed download for this devcode, taken on different hardware
# with local control enabled, which is what shows the inverter's own side of a
# pairing (#88). ``analysis_2449.json`` was taken before the download carried
# a ``local_control`` section at all.
LOCAL_EVIDENCE = (
    Path(__file__).resolve().parent.parent
    / "docs/evidence/devcodes/analysis_2449_local_control.json"
)


def _local_control_report() -> dict[str, Any]:
    payload = json.loads(LOCAL_EVIDENCE.read_text("utf-8"))
    devices = payload["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["devcode"] == DEVCODE
    return devices[0]["local_control"]


def test_the_charger_priority_is_paired_with_the_pi30_command() -> None:
    """Its two names differ by a letter, so nothing pairs it on spelling.

    "Charging Source Priority" on the platform against "Charger Source
    Priority" on the inverter: the declaration is what sends the write down
    the local link instead of through the cloud (#88).
    """
    assert local_control_setting(DEVCODE, "bat_charging_source") == (
        "charger_source_priority"
    )


def test_the_paired_setting_is_one_the_inverter_reports() -> None:
    """A pairing names a key in the inverter's own rating reply or nothing.

    This is the half of the evidence a declaration cannot be written without:
    the setting has to exist and carry a value, because the hybrid route only
    takes the local link for a setting the snapshot has a value for. A typo
    here would silently keep every write on the cloud.
    """
    report = _local_control_report()

    assert "charger_source_priority" in report["reported"]
    assert "charger_source_priority" not in report["not_reported"]


def test_nothing_else_on_the_platform_could_be_the_paired_control() -> None:
    """The other half: the pairing report found no candidate of its own.

    Where it does find one, the hybrid coordinator pairs them without a
    declaration. An empty candidate list is why this one needed evidence.
    """
    report = _local_control_report()
    entry = next(
        item
        for item in report["cloud_pairing"]
        if item["setting"] == "charger_source_priority"
    )

    assert entry["command"] == "PCP"
    assert entry["paired_by_name"] is None
    assert entry["candidates"] == []


def test_every_declared_option_is_one_the_local_command_accepts() -> None:
    """A code the command does not offer is refused, and the write stays put.

    The declared vocabulary is read back against the option list the inverter
    itself reported, so a renumbered list - devcode 2477's charger codes are
    not the PI30 ones - cannot pass unnoticed here (#87).
    """
    report = _local_control_report()
    entry = next(
        item
        for item in report["cloud_pairing"]
        if item["setting"] == "charger_source_priority"
    )
    accepted = set(entry["options"])

    declared = local_control_options(DEVCODE, "bat_charging_source")
    assert declared
    assert set(declared.values()) <= accepted


def test_the_option_the_owner_set_is_the_one_the_inverter_reported() -> None:
    """The entry that is observed rather than decoded from the ASCII rule.

    The reporter set Charging Source Priority to "Only Solar Charging
    Permitted" from Home Assistant and then took this download. The cloud
    control holds that value and the inverter reports 3 under PCP, which is
    "Only Solar" in its own list, so 12339 -> 3 is confirmed on hardware.
    """
    report = _local_control_report()
    entry = next(
        item
        for item in report["cloud_pairing"]
        if item["setting"] == "charger_source_priority"
    )

    assert entry["reported"] == "3"
    assert entry["options"]["3"] == "Only Solar"
    declared = local_control_options(DEVCODE, "bat_charging_source")
    assert declared
    assert declared["12339"] == "3"
