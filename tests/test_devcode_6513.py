"""Devcode 6513, a ZAMDON all-in-one with a lithium BMS link (#82).

The reporter's diagnostics download resolved 10 of 34 titles and dropped 18
that carry a unit, among them the whole BMS section and both PV strings. The
mappings below are read from that file, which is committed as
``docs/evidence/devcodes/analysis_6513.json``.
"""

from __future__ import annotations

from custom_components.dessmonitor.device_support import is_setting_reading
from custom_components.dessmonitor.device_support.device_registry import (
    apply_devcode_transformations,
    is_devcode_supported,
    needs_parameter_fetch,
)

DEVCODE = 6513

# Every title the download reported as reaching no entity.
REPORTED_UNMAPPED = [
    "Adaptive protocol identification",
    "BMS Lithium battery rated capacity",
    "BMS lithium battery SOH",
    "BMS lithium battery alarm information",
    "BMS lithium battery capacity SOC",
    "BMS lithium battery current",
    "BMS lithium battery voltage",
    "Input frequency",
    "Input voltage",
    "MPPT battery voltage",
    "MPPT discharge current",
    "Mains voltage",
    "Maximum charging current of the controller",
    "PV1 carging current",
    "PV1 low voltage",
    "PV1 voltagee",
    "PV2 carging current",
    "PV2 low voltage",
    "PV2 voltagee",
    "Remaining capacity of BMS lithium battery",
    "Temperature",
    "Total solar power generation",
    "Working state",
]

# The alarm words and the identity fields, which carry no unit and measure
# nothing. Each reads its own title back while the condition holds.
UNMEASURED_TITLES = {
    "Adaptive protocol identification",
    "BMS lithium battery alarm information",
    "Mains voltage",
    "PV1 low voltage",
    "PV2 low voltage",
}


def _resolved_key(title: str) -> str | None:
    from custom_components.dessmonitor.support_report import resolved_key_for

    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reported_title_is_accounted_for() -> None:
    """Each one reaches a sensor, is a declared setting, or measures nothing."""
    unaccounted = [
        title
        for title in REPORTED_UNMAPPED
        if _resolved_key(title) is None
        and not is_setting_reading(DEVCODE, title)
        and title not in UNMEASURED_TITLES
    ]

    assert unaccounted == []


def test_the_three_battery_voltages_stay_three_sensors() -> None:
    """The inverter, the controller and the pack each measure it (50.4, 50.2, 49.94)."""
    assert _resolved_key("Battery voltage") == "Battery Voltage"
    assert _resolved_key("MPPT battery voltage") == "MPPT Battery Voltage"
    assert _resolved_key("BMS lithium battery voltage") == "BMS battery voltage"


def test_the_bms_section_reaches_its_own_sensors() -> None:
    assert _resolved_key("BMS lithium battery capacity SOC") == "State of Charge"
    assert _resolved_key("BMS lithium battery current") == "BMS battery current"
    assert (
        _resolved_key("Remaining capacity of BMS lithium battery")
        == "BMS Remaining Capacity"
    )
    assert _resolved_key("BMS Lithium battery rated capacity") == "BMS Rated Capacity"
    assert _resolved_key("BMS lithium battery SOH") == "BMS State of Health"


def test_the_vendor_s_spelling_is_mapped_as_sent() -> None:
    assert _resolved_key("PV1 voltagee") == "PV1 Voltage"
    assert _resolved_key("PV2 voltagee") == "PV2 Voltage"
    assert _resolved_key("PV1 carging current") == "PV1 Charger Current"
    assert _resolved_key("PV2 carging current") == "PV2 Charger Current"


def test_the_lifetime_yield_does_not_take_over_the_summary_s_entity() -> None:
    """Energy Total is already published from the summary endpoint (#75, #79)."""
    assert (
        _resolved_key("Total solar power generation") == "PV Cumulative Power Generation"
    )


def test_the_controller_limit_is_a_rating_not_a_setting() -> None:
    """It reads 100 A against controls of 90 A and 500, so it is neither's readback."""
    assert (
        _resolved_key("Maximum charging current of the controller")
        == "Controller Max Charging Current"
    )
    assert not is_setting_reading(DEVCODE, "Maximum charging current of the controller")


def test_the_observed_operating_mode_is_mapped() -> None:
    """The download was taken with the mains absent: 4.0 V and 0.0 Hz."""
    point = apply_devcode_transformations(
        DEVCODE, {"title": "Working state", "val": "Inverted state", "unit": ""}
    )

    assert point["title"] == "Operating mode"
    assert point["val"] == "Battery"


def test_an_unregistered_state_is_published_as_the_collector_spells_it() -> None:
    point = apply_devcode_transformations(
        DEVCODE, {"title": "Working state", "val": "Mains state", "unit": ""}
    )

    assert point["val"] == "Mains state"


def test_no_separate_parameter_fetch_is_needed() -> None:
    assert not needs_parameter_fetch(DEVCODE)
