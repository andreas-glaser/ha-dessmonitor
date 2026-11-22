"""Control entities a nobody has reviewed are registered disabled (#90).

Every field an account's control template advertises becomes an entity, and
the template belongs to the platform rather than to this integration. The
devcode 567 account in #89 was handed 96 of them enabled, among them shutdown,
start, reset, firmware upgrade, "format M4 SPI flash" and three levels each of
grid over- and undervoltage and over- and underfrequency protection with their
trip times. Its owner found them and disabled them by hand.

So the default is off and a profile turns it on for the template it has read.
The tests that matter here are the two that cannot be checked by reading the
code: that a profile claiming to have reviewed a template has one committed,
and that every field it protects is really in that template. A protected id
with a typo in it leaves a destructive control enabled and nothing else would
say so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import control_enabled_by_default
from custom_components.dessmonitor.device_support.device_registry import (
    get_devcode_config,
    get_supported_devcodes,
)

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "docs/evidence/devcodes"

# The two devcodes whose templates were read and deliberately left with
# nothing enabled: every field in both is an installer's, not an owner's.
INSTALLER_TEMPLATES = (518, 567)


def _templates() -> dict[int, dict[str, str]]:
    """Field id -> name, per devcode, from every committed download."""
    found: dict[int, dict[str, str]] = {}
    for path in sorted(EVIDENCE_DIR.glob("analysis_*.json")):
        payload = json.loads(path.read_text("utf-8"))
        for device in payload.get("data", payload).get("devices") or []:
            devcode = device.get("devcode")
            for control in device.get("control_fields") or []:
                field_id = control.get("id")
                if isinstance(devcode, int) and isinstance(field_id, str):
                    found.setdefault(devcode, {})[field_id] = control.get("name", "")
    return found


def _reviewed() -> list[int]:
    return [
        devcode
        for devcode in sorted(get_supported_devcodes())
        if (get_devcode_config(devcode) or {}).get("controls_reviewed")
    ]


def _protected(devcode: int) -> frozenset[str]:
    declared = (get_devcode_config(devcode) or {}).get("protected_controls")
    return frozenset(declared or ())


def test_a_devcode_with_no_profile_publishes_its_controls_disabled() -> None:
    """The account that most needs the protection is the one nobody has read.

    This is the whole point: the rule cannot key on whether a profile exists,
    or adding one would hand the fields back.
    """
    assert control_enabled_by_default(9999, "shutdown") is False


def test_a_profile_that_declares_nothing_publishes_its_controls_disabled() -> None:
    """Devcode 659 has a profile and no control declaration, so off."""
    assert control_enabled_by_default(659, "anything") is False


@pytest.mark.parametrize("devcode", INSTALLER_TEMPLATES)
def test_an_installer_template_has_nothing_enabled(devcode: int) -> None:
    """Both templates were read and nothing in either is an owner's setting.

    Devcode 567 is the grid protection points, the fault mask words, the four
    internal debugging parameters and the commissioning commands. Devcode 518
    is the grid thresholds, the safety standard, the power limits and the HMI
    password. Neither declares itself reviewed, so every field stays off.
    """
    template = _templates().get(devcode) or {}
    assert template, f"devcode {devcode} has no committed template"

    enabled = [
        field_id
        for field_id in template
        if control_enabled_by_default(devcode, field_id)
    ]

    assert enabled == []


def test_devcode_567_publishes_none_of_its_ninety_six_fields_enabled() -> None:
    """The account from #89, stated as a count so the regression is visible."""
    template = _templates()[567]

    assert len(template) == 96
    assert not any(control_enabled_by_default(567, field) for field in template)


def test_at_least_one_profile_has_reviewed_its_template() -> None:
    """Guards against the declaration being dropped and every control going
    dark, which the tests above would not catch on their own."""
    assert _reviewed()


@pytest.mark.parametrize("devcode", _reviewed())
def test_a_reviewed_devcode_has_a_committed_template(devcode: int) -> None:
    """A profile cannot have read a template that is not committed here.

    The declaration says a person looked at the fields and decided. The
    evidence for that is the download it was read from.
    """
    assert devcode in _templates()


@pytest.mark.parametrize("devcode", _reviewed())
def test_every_protected_field_is_in_that_devcodes_template(devcode: int) -> None:
    """The test this file exists for.

    A protected id that matches nothing is a destructive control published
    enabled, and the only symptom is an owner finding it. Nothing else checks
    the spelling.
    """
    template = _templates()[devcode]
    missing = sorted(_protected(devcode) - set(template))

    assert missing == [], f"devcode {devcode} protects fields it does not have"


@pytest.mark.parametrize("devcode", _reviewed())
def test_a_reviewed_devcode_enables_something(devcode: int) -> None:
    """A reviewed owner template is meant to stay usable.

    A profile that reviewed a template and then protected every field in it
    is really saying the template is an installer's, and the honest
    declaration for that is the one devcodes 518 and 567 make: no review, so
    nothing enabled. Devcode 697 is the closest to the line and protects
    exactly half of its 24 fields, because nine of them are the factory
    calibration coefficients.
    """
    template = _templates()[devcode]
    enabled = [
        field_id
        for field_id in template
        if control_enabled_by_default(devcode, field_id)
    ]

    assert enabled
    assert len(enabled) >= len(template) / 2


def test_the_protected_fields_are_the_ones_that_act_rather_than_set() -> None:
    """A spot check in plain terms, so the intent is readable.

    These are the four shapes the declarations cover: restoring defaults,
    clearing a lifetime counter, switching the inverter off, and a
    grid-compliance setting a grid operator approved the unit against.
    """
    assert control_enabled_by_default(2449, "sys_set_default") is False
    assert control_enabled_by_default(6544, "sys_eybond_ctrl_44026") is False
    assert control_enabled_by_default(2500, "shutdown_work") is False
    assert control_enabled_by_default(2500, "grid_protect_standard") is False

    # And the ordinary settings beside them are untouched.
    assert control_enabled_by_default(2449, "bat_battery_type") is True
    assert control_enabled_by_default(2500, "battery_type") is True


def test_a_calibration_coefficient_is_protected() -> None:
    """Devcode 697 mixes owner settings with the factory calibration.

    A coefficient does not change what the inverter does, it changes what the
    inverter reports, so a nudged one falsifies every reading downstream of it
    with nothing to say so.
    """
    for field in (
        "grid_voltage_calibration_coefficient",
        "battery_voltage_calibration_coefficient",
        "load_current_calibration_coefficient",
    ):
        assert control_enabled_by_default(697, field) is False

    assert control_enabled_by_default(697, "charger_source_priority") is True


def _number_entity(devcode: int, param_id: str):
    from custom_components.dessmonitor.number import DessMonitorNumber

    return DessMonitorNumber(
        MagicMock(),
        "TEST-SN",
        {"devcode": devcode, "alias": "Roof"},
        {"pn": "TEST-PN"},
        "Some Setting",
        "Some Setting",
        param_id,
        "10",
        "V",
        None,
    )


def test_the_flag_reaches_a_real_control_entity() -> None:
    """The helper is only useful if the platforms actually set the attribute."""
    protected: Any = _number_entity(2449, "sys_set_default")
    ordinary: Any = _number_entity(2449, "bat_charging_bulk_voltage")

    assert protected.entity_registry_enabled_default is False
    assert ordinary.entity_registry_enabled_default is True


def test_an_unreviewed_devcodes_control_entity_is_disabled() -> None:
    entity: Any = _number_entity(567, "grid_level_overvoltage_protection_point")

    assert entity.entity_registry_enabled_default is False
