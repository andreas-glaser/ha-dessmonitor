"""DessMonitor Data Collector (devcode 2477)."""

from __future__ import annotations

import re
from typing import Any

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2477)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
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


DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "control_options_filter": filter_control_options,
}
