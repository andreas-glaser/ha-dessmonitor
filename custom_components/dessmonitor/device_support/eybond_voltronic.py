"""The vocabulary Eybond collectors use for a Voltronic PI30 inverter.

Eybond makes the collector and runs the cloud; the inverter behind it speaks
Voltronic's PI30 protocol, and the collector renders that protocol's fields as
the titles this module names. Devcodes 2477 and 2341 are two collectors of this
family, and they send the same titles, spelling mistakes included, and the same
control field ids down to the vendor's ``floting``.

Two devcodes with one vocabulary is the reason this file exists. Devcode 2341
was reported twice on the same day, by an EASUN owner and a PowMr owner on two
firmwares (#72, #73), and all three devices sent an identical set of 45
unmapped titles of which 41 were already named in the devcode 2477 profile.
Copying that profile would have left two lists to keep in step; the evidence
says there is one list.

A devcode module still owns what is its own: the hardware it names, and the
operating modes its own collector has been seen to report. Nothing here is a
guess about a devcode that has not been measured - a profile opts in by
importing these tables, so adding a devcode to this family stays a decision
backed by its own download.
"""

from __future__ import annotations

import re
from typing import Any

# The collector reports the setpoints and the nameplate ratings beside the live
# readings. Output and charger priority arrive as the short forms below.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "Utility": "Utility First",
    "Solar": "Solar First",
    "SBU": "Solar - Battery - Utility",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "Solar priority": "Solar First",
    "Solar and mains": "Solar and Utility",
    "Solar only": "Only Solar",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Input Frequency": "Grid Frequency",
    "AC Input Voltage": "Grid Voltage",
    "AC Output Load": "Load Percent",
    "Battery Capacity": "State of Charge",
    "Output Source Priority": "Output priority",
    "PV Input Power": "PV Charge Power",
    "PV Input Voltage": "PV Voltage",
    "Working State": "Operating mode",
    # Nameplate ratings. The collector labels each with a unit, so each is a
    # reading, and none of them is a control on this family. "Nonimal" is the
    # vendor's spelling, not a typo here.
    "Nominal AC Current": "grid rated current",
    "Nominal AC Voltage": "grid rated voltage",
    "Nominal Output Current": "rated current",
    "Nominal Output Frequency": "rated frequency",
    "Nominal Output Voltage": "rated voltage",
    "Nonimal Output Active Power": "rated power",
    "Nonimal Output Apparent Power": "rated apparent power",
    "Rated Battery Voltage": "battery rated voltage",
    # Status texts the vendor app shows and nothing here published.
    "Mains Status": "Grid Status",
}

# Setpoints this family returns among the telemetry, each the value of a
# control the account publishes. A setting is not a reading whichever way the
# vendor delivers it, and counting these as dropped readings is what made the
# support report tell these owners that readings were missing (#61, #72, #73).
#
# A setting is declared from the reading title the collector sends, which is
# not always how it names the same setting as a control: it reports "Beeps
# While Primary Source Interupt" as a reading and "...Interrupt" as a control,
# "Transfer To Bypass @ Overload" against "Transfer To Bypass Overload", and
# "Auto Return To Default Display Screen" against "Return To The Main LCD
# Page".
SETTING_READINGS: set[str] = {
    "AC Input Range",
    "Auto Return To Default Display Screen",
    "Battery Equalization",
    "Battery Equalization Activated Immediately",
    "Battery Equalization Interval",
    "Battery Equalization Voltage",
    "Battery Equalized Time",
    "Battery Equalized Timeout",
    "Battery Type",
    "Beeps While Primary Source Interupt",
    "Bulk Charging Voltage",
    "Buzzer Alarm",
    "Comeback Battery Mode Voltage Point Under (SBU Priority)",
    "Comeback Utility Mode Voltage Point Under (SBU Priority)",
    "Floating Charging Voltage",
    "LCD Backlight",
    "Low Battery Cut-off Voltage",
    "Max Total Charge Current",
    "Max Utility Charge Current",
    "Over Temperature Auto Restart",
    "Overload Auto Restart",
    "Power Saving Mode",
    "Record Fault Code",
    "Transfer To Bypass @ Overload",
}

# Issue #40's API lists separate option groups for multiple hardware variants.
# Keep only options the API supplied within the reported nominal-voltage group.
_CHARGE_VOLTAGE_RANGES = {24: (25.0, 31.5), 48: (48.0, 61.0)}
_BATTERY_VOLTAGE_RANGES = {
    "bat_sp_battery_equalization_voltage": _CHARGE_VOLTAGE_RANGES,
    "bat_sp_bulk_charging_voltage": _CHARGE_VOLTAGE_RANGES,
    "bat_sp_floting_charging_voltage": _CHARGE_VOLTAGE_RANGES,
    "bat_sp_battery_mode_voltage": {24: (24.0, 29.0), 48: (48.0, 58.0)},
    "bat_sp_utility_mode_voltage": {24: (21.0, 25.5), 48: (42.0, 51.0)},
    "bat_sp_low_battery_voltage": {24: (20.0, 24.0), 48: (40.0, 48.0)},
}
_RATED_VOLTAGE_RE = re.compile(r"([0-9]+)(?:\.0+)?\s*V?", re.IGNORECASE)
_BATTERY_PIECE_RE = re.compile(
    r"([0-9]+)(?:\.0+)?\s*V(?:\s*\([^()]+\))?", re.IGNORECASE
)
_OPTION_VOLTAGE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*V", re.IGNORECASE)


def _rated_battery_voltage(data: list[dict[str, Any]]) -> int:
    ratings: set[int] = set()
    for point in data:
        title = str(point.get("title", "")).strip().casefold()
        if title not in ("rated battery voltage", "battery piece"):
            continue
        raw = point.get("val")
        if raw in (None, "", "--", "-"):
            continue
        pattern = (
            _RATED_VOLTAGE_RE if title == "rated battery voltage" else _BATTERY_PIECE_RE
        )
        match = pattern.fullmatch(str(raw).strip())
        if match is None:
            raise ValueError("invalid rated battery voltage metadata")
        rating = int(match.group(1))
        if rating not in (24, 48):
            raise ValueError("unsupported rated battery voltage; expected 24 V or 48 V")
        ratings.add(rating)
    if len(ratings) != 1:
        raise ValueError("missing or conflicting rated battery voltage metadata")
    return ratings.pop()


def filter_control_options(
    param_id: str, options: dict[str, str], data: list[dict[str, Any]]
) -> dict[str, str]:
    """Select the verified variant's voltage options without rewriting API keys."""
    ranges = _BATTERY_VOLTAGE_RANGES.get(param_id)
    if ranges is None:
        return options
    low, high = ranges[_rated_battery_voltage(data)]
    selected: dict[str, str] = {}
    for key, label in options.items():
        match = _OPTION_VOLTAGE_RE.fullmatch(str(label).strip())
        if match is None:
            raise ValueError("invalid battery voltage option label")
        if low <= float(match.group(1)) <= high:
            selected[key] = label
    if not selected:
        raise ValueError("no battery voltage options match the rated voltage")
    return selected
