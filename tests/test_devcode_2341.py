"""Devcode 2341, reported twice on the same day (#72, #73).

An EASUN owner on collector firmware 3.2.1.1 and a PowMr owner on 3.1.1.0
attached three device diagnostics downloads between them, and all three devices
reported an identical set of 45 titles that reached no entity. 41 of those were
already named by the devcode 2477 profile, and the control template agreed down
to the vendor's ``bat_sp_floting_charging_voltage``, so the two devcodes share
one vocabulary rather than two copies of it.

The titles below are the ones those downloads named. Units are not asserted
here: those downloads carried none, which is the gap the support report in the
device download now closes.
"""

from __future__ import annotations

from custom_components.dessmonitor.device_support import is_setting_reading
from custom_components.dessmonitor.device_support.device_registry import (
    apply_devcode_transformations,
    is_devcode_supported,
    needs_parameter_fetch,
)
from custom_components.dessmonitor.device_support.eybond_voltronic import (
    filter_control_options,
)

DEVCODE = 2341

# Every title the three downloads reported as reaching no entity.
REPORTED_UNMAPPED = [
    "AC Input Frequency",
    "AC Input Range",
    "AC Input Voltage",
    "AC Output Load",
    "Auto Return To Default Display Screen",
    "Battery Capacity",
    "Battery Equalization",
    "Battery Equalization Activated Immediately",
    "Battery Equalization Interval",
    "Battery Equalization Voltage",
    "Battery Equalized Time",
    "Battery Equalized Timeout",
    "Battery Piece",
    "Battery Type",
    "Beeps While Primary Source Interupt",
    "Bulk Charging Voltage",
    "Buzzer Alarm",
    "Comeback Battery Mode Voltage Point Under (SBU Priority)",
    "Comeback Utility Mode Voltage Point Under (SBU Priority)",
    "Floating Charging Voltage",
    "LCD Backlight",
    "Low Battery Cut-off Voltage",
    "Machine Type",
    "Main CPU Version",
    "Mains Status",
    "Max Total Charge Current",
    "Max Utility Charge Current",
    "Nominal AC Current",
    "Nominal AC Voltage",
    "Nominal Output Current",
    "Nominal Output Frequency",
    "Nominal Output Voltage",
    "Nonimal Output Active Power",
    "Nonimal Output Apparent Power",
    "Output Source Priority",
    "Over Temperature Auto Restart",
    "Overload Auto Restart",
    "PV Input Power",
    "PV Input Voltage",
    "Power Saving Mode",
    "Rated Battery Voltage",
    "Record Fault Code",
    "Secondary CPU Version",
    "Transfer To Bypass @ Overload",
    "Working State",
]

# The four that identify the hardware rather than measuring anything. Neither
# this devcode's downloads nor devcode 2477's committed evidence gives any of
# them a unit, so none of them holds a Repairs card open.
IDENTITY_TITLES = {
    "Battery Piece",
    "Machine Type",
    "Main CPU Version",
    "Secondary CPU Version",
}


def _resolved_key(title: str) -> str | None:
    from custom_components.dessmonitor.support_report import resolved_key_for

    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reported_title_is_accounted_for() -> None:
    """Each one reaches a sensor, is a declared setting, or names the hardware.

    This is the check that was missing when devcode 6514 shipped with one
    sensor and dropped 58 of its 76 titles in silence (#35, #56).
    """
    unaccounted = [
        title
        for title in REPORTED_UNMAPPED
        if _resolved_key(title) is None
        and not is_setting_reading(DEVCODE, title)
        and title not in IDENTITY_TITLES
    ]

    assert unaccounted == []


def test_the_telemetry_titles_reach_the_sensors_the_owners_asked_for() -> None:
    """Both reporters named these: SOC, PV, grid, output and the mode."""
    assert _resolved_key("Battery Capacity") == "State of Charge"
    assert _resolved_key("AC Input Voltage") == "Grid Voltage"
    assert _resolved_key("AC Input Frequency") == "Grid Frequency"
    assert _resolved_key("PV Input Voltage") == "PV Voltage"
    assert _resolved_key("PV Input Power") == "PV Charge Power"
    assert _resolved_key("AC Output Load") == "Load Percent"
    assert _resolved_key("Working State") == "Operating mode"
    assert _resolved_key("Mains Status") == "Grid Status"
    assert _resolved_key("Output Source Priority") == "Output priority"


def test_the_nameplate_ratings_become_their_own_sensors() -> None:
    """A rating is a fact about the hardware, not a setting (#53)."""
    assert _resolved_key("Nominal AC Voltage") == "grid rated voltage"
    assert _resolved_key("Nominal AC Current") == "grid rated current"
    assert _resolved_key("Nominal Output Voltage") == "rated voltage"
    assert _resolved_key("Nominal Output Current") == "rated current"
    assert _resolved_key("Nominal Output Frequency") == "rated frequency"
    assert _resolved_key("Nonimal Output Active Power") == "rated power"
    assert _resolved_key("Nonimal Output Apparent Power") == "rated apparent power"
    assert _resolved_key("Rated Battery Voltage") == "battery rated voltage"


def test_the_setpoints_are_settings_not_missing_readings() -> None:
    """They are already published as number and select entities."""
    for title in (
        "Bulk Charging Voltage",
        "Floating Charging Voltage",
        "Low Battery Cut-off Voltage",
        "Max Total Charge Current",
        "Max Utility Charge Current",
        "Battery Type",
        "AC Input Range",
        # Spelled one way as a reading and another as a control.
        "Beeps While Primary Source Interupt",
        "Transfer To Bypass @ Overload",
        "Auto Return To Default Display Screen",
    ):
        assert is_setting_reading(DEVCODE, title), title


def test_the_observed_operating_mode_is_mapped() -> None:
    """Both reporters' mains was out, so this is the only mode seen."""
    point = apply_devcode_transformations(
        DEVCODE, {"title": "Working State", "val": "Invert Mode", "unit": ""}
    )

    assert point["val"] == "Battery"


def test_the_priorities_use_this_family_s_short_forms() -> None:
    priority = apply_devcode_transformations(
        DEVCODE, {"title": "Output Source Priority", "val": "SBU", "unit": ""}
    )
    charger = apply_devcode_transformations(
        DEVCODE, {"title": "Charger Source Priority", "val": "Solar only", "unit": ""}
    )

    assert priority["val"] == "Solar - Battery - Utility"
    assert charger["val"] == "Only Solar"


def test_no_separate_parameter_fetch_is_needed() -> None:
    """Its parameters endpoint repeats readings the telemetry call carries."""
    assert not needs_parameter_fetch(DEVCODE)


def test_the_voltage_options_are_narrowed_to_the_reporters_24_v_hardware() -> None:
    """The template offers the 24 V and 48 V ranges in one list.

    Both reporters' inverters are 24 V units: bulk 28.8 V, float 27.2 V, and a
    battery reading 24.3 V. Offering them 61.0 V would be offering a setting
    that belongs to other hardware.
    """
    options = {"25.0": "25.0V", "31.5": "31.5V", "48.0": "48.0V", "61.0": "61.0V"}
    data = [{"title": "Rated Battery Voltage", "val": "24"}]

    selected = filter_control_options("bat_sp_bulk_charging_voltage", options, data)

    assert selected == {"25.0": "25.0V", "31.5": "31.5V"}
