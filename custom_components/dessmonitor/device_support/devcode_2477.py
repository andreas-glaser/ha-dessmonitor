"""Eybond Data Collector (devcode 2477).

Voltronic-family inverter on the DessMonitor platform. Evidence for the rating
and setting titles below is the diagnostics download in
``docs/evidence/devcodes/analysis_2477.json`` (#61).

``queryDeviceLastData`` returns the inverter's nameplate ratings and its own
setpoints alongside the live readings, as devcode 2452 does. The ratings are
facts about the hardware and become diagnostic sensors; the setpoints are
settings the account publishes as number and select entities, so they are
declared in ``SETTING_READINGS`` rather than mapped onto a sensor each. Of the
sixty-three titles this collector sent, twenty-two reached an entity and the
report told the owner that nineteen readings were missing when none were.

The collector's reading titles and its control-field names are not spelled the
same, so a setting is declared from the reading title it sends: it reports
"Beeps While Primary Source Interupt" as a reading and "...Interrupt" as a
control, and "Transfer To Bypass @ Overload" against "Transfer To Bypass
Overload".
"""

from __future__ import annotations

import re
from typing import Any

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2477)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": [],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

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

OPERATING_MODE_MAPPING: dict[str, str] = {"Line Mode": "Line"}

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
    # reading, and none of them is a control on this devcode. "Nonimal" is the
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

VALUE_TRANSFORMATIONS: dict = {}
PARAMETER_SENSOR_NAMES: set[str] = set()

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


# Setpoints this collector returns among the telemetry, each the value of a
# control the account publishes. A setting is not a reading whichever way the
# vendor delivers it, and counting these as dropped readings is what made the
# support report tell this owner that readings were missing (#61).
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

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "control_options_filter": filter_control_options,
    "setting_readings": SETTING_READINGS,
}
