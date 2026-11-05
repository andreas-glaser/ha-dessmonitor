"""Controls whose reported value is spelled unlike the options they offer.

Devcode 2376 answers 60.0 for an Output Frequency keyed "50.00" and "60.00",
and 229.8 - the live output voltage - for an Output Voltage offering 220, 230
and 240. The first is the same setting in another spelling and must reach the
entity; the second is not a setting at all and must not. Evidence is the
diagnostics download in ``docs/evidence/devcodes/analysis_2376.json``, taken on
four parallel POW-HVM6.2K-48V-LIP inverters (#61).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.dessmonitor import _format_control_fields
from custom_components.dessmonitor.control_values import option_key_for, setting_value
from custom_components.dessmonitor.select import _async_build_select_entities

DEVCODE = 2376

# As the download reports them.
FREQUENCY = {
    "type": "options",
    "id": "bse_eybond_ctrl_65",
    "options": {"50.00": "50Hz", "60.00": "60Hz"},
}
VOLTAGE = {
    "type": "options",
    "id": "bse_eybond_ctrl_64",
    "options": {"220.0": "220Vac", "230.0": "230Vac", "240.0": "240Vac"},
}


def _coordinator(controls: dict, values: dict, readings: list) -> MagicMock:
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.cloud_revision = 1
    coordinator.data = {
        "TEST-SN": {
            "collector": {"pn": "TEST-PN"},
            "device": {"devcode": DEVCODE, "devaddr": 1},
            "data": readings,
        }
    }
    coordinator.async_get_controls_with_values = AsyncMock(
        return_value=(controls, values)
    )
    coordinator.ctrl_value_cache = {"TEST-SN": dict(values)}
    coordinator.api.set_device_control_value = AsyncMock(return_value={"err": 0})
    return coordinator


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The vendor's own answer for this control, which never matched.
        (60.0, "60.00"),
        ("60.0", "60.00"),
        ("60", "60.00"),
        # Already the API's spelling, or its label.
        ("60.00", "60.00"),
        ("60Hz", "60Hz"),
    ],
)
def test_a_differently_spelled_number_is_the_same_setting(raw, expected) -> None:
    assert setting_value(FREQUENCY, raw) == expected


@pytest.mark.parametrize("raw", [229.8, "229.8", "231.3"])
def test_a_live_measurement_is_not_a_setting(raw) -> None:
    """The collector answers this control's name with the measured voltage.

    Accepting it would show a setting the inverter does not have, and snapping
    it to the nearest option would report one it was never set to.
    """
    assert setting_value(VOLTAGE, raw) is None


def test_the_key_returned_is_the_one_a_write_has_to_send() -> None:
    """Rewriting a vendor key is what made integer fields reject a value (#49)."""
    assert option_key_for(FREQUENCY["options"], "60") == "60.00"
    assert option_key_for(VOLTAGE["options"], "230") == "230.0"
    assert option_key_for(FREQUENCY["options"], "Enable") is None


def test_a_unit_suffixed_label_is_not_read_as_a_number() -> None:
    """Otherwise "220Vac" would match a bare 220 for the wrong control."""
    options = {"0": "220Vac", "1": "230Vac"}

    assert option_key_for(options, "230") is None


async def test_the_frequency_select_shows_the_reported_value() -> None:
    coordinator = _coordinator(
        {"Output Frequency": FREQUENCY},
        {"bse_eybond_ctrl_65": setting_value(FREQUENCY, 60.0)},
        [{"title": "Output Frequency", "val": "60.0", "unit": "Hz"}],
    )

    (entity,) = await _async_build_select_entities(coordinator, set())

    assert entity.options == ["50Hz", "60Hz"]
    assert entity.current_option == "60Hz"


async def test_the_voltage_select_reports_no_value_rather_than_the_measurement() -> (
    None
):
    coordinator = _coordinator(
        {"Output Voltage": VOLTAGE},
        {"bse_eybond_ctrl_64": setting_value(VOLTAGE, 229.8)},
        [{"title": "Output Voltage", "val": "229.8", "unit": "V"}],
    )

    (entity,) = await _async_build_select_entities(coordinator, set())

    assert entity.current_option is None
    assert entity.extra_state_attributes["value_status"] == "not_loaded"


async def test_the_voltage_select_fills_from_the_declared_reading() -> None:
    """The setpoint is in telemetry, so no live read is needed for it.

    Leaving it unread keeps the field on the coordinator's list of values to
    read again on every cloud revision, and each of those reads is a live
    request over the collector's single-transaction link.
    """
    coordinator = _coordinator(
        {"Output Voltage": VOLTAGE},
        {},
        [
            {"title": "Output Voltage", "val": "229.8", "unit": "V"},
            {"title": "Output Voltage Setting", "val": "230.0", "unit": "V"},
        ],
    )

    (entity,) = await _async_build_select_entities(coordinator, set())
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity._handle_coordinator_update()

    assert entity.current_option == "230Vac"
    assert coordinator.ctrl_value_cache["TEST-SN"]["bse_eybond_ctrl_64"] == "230.0"


async def test_a_measurement_alone_still_leaves_the_control_unread() -> None:
    """Without the setpoint there is nothing trustworthy to show."""
    coordinator = _coordinator(
        {"Output Voltage": VOLTAGE},
        {},
        [{"title": "Output Voltage", "val": "229.8", "unit": "V"}],
    )

    (entity,) = await _async_build_select_entities(coordinator, set())
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity._handle_coordinator_update()

    assert entity.current_option is None


def test_the_download_reports_what_the_entity_shows() -> None:
    """A file that claims a value the entity rejects sends a reader nowhere.

    The diagnostics took any telemetry reading whose title matched a control
    name as that control's value, without checking it against the options, so
    the download presented 229.8 V as the Output Voltage setting while Home
    Assistant showed none for it (#61).
    """
    readings = [
        {"title": "Output Voltage", "val": "229.8", "unit": "V"},
        {"title": "Output Frequency", "val": "60.0", "unit": "Hz"},
    ]

    formatted = _format_control_fields(
        {"Output Voltage": VOLTAGE, "Output Frequency": FREQUENCY},
        readings,
        None,
        DEVCODE,
    )

    assert formatted["Output Voltage"]["value"] == "Not read"
    # The frequency is the same setting in another spelling, so it is reported.
    assert formatted["Output Frequency"]["value"] == "60Hz"


def test_the_download_uses_the_declared_reading_too() -> None:
    """The file and the entity must not disagree about a control's value."""
    readings = [
        {"title": "Output Voltage", "val": "229.8", "unit": "V"},
        {"title": "Output Voltage Setting", "val": "230.0", "unit": "V"},
    ]

    formatted = _format_control_fields(
        {"Output Voltage": VOLTAGE}, readings, None, DEVCODE
    )

    assert formatted["Output Voltage"]["value"] == "230Vac"


def test_a_devcode_without_a_declaration_is_unaffected() -> None:
    """The mechanism is generic; only a profile that declares one uses it."""
    from custom_components.dessmonitor.device_support import control_value_reading

    assert control_value_reading(DEVCODE, "bse_eybond_ctrl_64") == (
        "Output Voltage Setting"
    )
    assert control_value_reading(DEVCODE, "bse_eybond_ctrl_65") is None
    assert control_value_reading(2477, "bse_eybond_ctrl_64") is None
    assert control_value_reading(None, "bse_eybond_ctrl_64") is None
