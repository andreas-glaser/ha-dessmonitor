"""Devcode 2451, an Axpert MKS IV 5600VA reported by a Mecer owner (#74).

The card said sixteen readings were missing. None was: the collector returns
the inverter's nameplate ratings and its own setpoints among the telemetry,
which is the same shape as devcodes 2452 (#53), 2477 (#61) and 6514 (#69).

The titles here are the twenty-four the reporter's download listed as reaching
no entity. Their units are not asserted: that download carries none, which is
the gap the support report in the device download now closes. The split
between the sixteen that carry a unit and the eight that do not comes from the
CLI summary quoted in the issue.
"""

from __future__ import annotations

from custom_components.dessmonitor.device_support import is_setting_reading
from custom_components.dessmonitor.device_support.device_registry import (
    is_devcode_supported,
)
from custom_components.dessmonitor.support_report import resolved_key_for

DEVCODE = 2451

REPORTED_UNMAPPED = [
    "AC Input Range",
    "AC Output Rating Active Power",
    "AC Output Rating Apparent Power",
    "AC Output Rating Current",
    "AC Output Rating Frequency",
    "AC Output Rating Voltage",
    "AC2 Output Status",
    "Battery Bulk Voltage",
    "Battery Float Voltage",
    "Battery Rating Voltage",
    "Battery Re-Charge Voltage",
    "Battery Re-Discharge Voltage",
    "Battery Type",
    "Battery Voltage From SCC",
    "Grid Input Current",
    "Grid Rating Current",
    "Grid Rating Voltage",
    "Machine Type",
    "Main CPU Firmware Version",
    "Max AC Charging Current",
    "Max Charging Current",
    "Model",
    "Parallel Max Num",
    "Secondary CPU Firmware Version",
]

# The ones that identify the hardware or report a bare status. The reporter's
# collector sends none of these with a unit, so none holds the card open.
IDENTITY_TITLES = {
    "AC2 Output Status",
    "Machine Type",
    "Main CPU Firmware Version",
    "Model",
    "Parallel Max Num",
    "Secondary CPU Firmware Version",
}


def _key(title: str) -> str | None:
    return resolved_key_for(DEVCODE, {"title": title, "val": "1"})


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE)


def test_every_reported_title_is_accounted_for() -> None:
    """Each reaches a sensor, is a declared setting, or names the hardware."""
    unaccounted = [
        title
        for title in REPORTED_UNMAPPED
        if _key(title) is None
        and not is_setting_reading(DEVCODE, title)
        and title not in IDENTITY_TITLES
    ]

    assert unaccounted == []


def test_the_nameplate_ratings_become_their_own_sensors() -> None:
    """A rating is a fact about the hardware, not a setting (#53)."""
    assert _key("AC Output Rating Active Power") == "rated power"
    assert _key("AC Output Rating Apparent Power") == "rated apparent power"
    assert _key("AC Output Rating Current") == "rated current"
    assert _key("AC Output Rating Frequency") == "rated frequency"
    assert _key("Battery Rating Voltage") == "battery rated voltage"
    assert _key("Grid Rating Current") == "grid rated current"
    assert _key("Grid Rating Voltage") == "grid rated voltage"


def test_the_output_rating_voltage_is_a_setting_as_on_devcode_2452() -> None:
    """It tracks the writable Output Voltage control rather than the hardware."""
    assert is_setting_reading(DEVCODE, "AC Output Rating Voltage")
    assert _key("AC Output Rating Voltage") is None


def test_the_two_real_readings_reach_sensors() -> None:
    """The only two of the sixteen that are neither a rating nor a setpoint."""
    assert _key("Grid Input Current") == "grid current"
    assert _key("Battery Voltage From SCC") == "Battery Voltage From SCC"


def test_the_setpoints_are_settings_not_missing_readings() -> None:
    """Declared from the reading title, which is not the control's spelling.

    It reports "Battery Bulk Voltage" against a "Bulk Charging Voltage"
    control, and "Battery Re-Charge Voltage" against "Back to Grid Voltage".
    """
    for title in (
        "AC Input Range",
        "Battery Bulk Voltage",
        "Battery Float Voltage",
        "Battery Re-Charge Voltage",
        "Battery Re-Discharge Voltage",
        "Battery Type",
        "Max AC Charging Current",
        "Max Charging Current",
    ):
        assert is_setting_reading(DEVCODE, title), title


def test_the_battery_voltage_from_scc_is_not_the_battery_voltage() -> None:
    """Axpert hardware reports both, and they differ while charging."""
    assert _key("Battery Voltage From SCC") != _key("Battery Voltage")


def test_no_other_devcode_inherits_these_declarations() -> None:
    assert not is_setting_reading(2449, "Battery Bulk Voltage")
    assert not is_setting_reading(6515, "Max Charging Current")
