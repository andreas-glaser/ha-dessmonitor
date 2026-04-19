"""DessMonitor Data Collector (devcode 2507)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2507)",
    "description": "DessMonitor data collector/gateway (WiFi)",
    "manufacturer": "DessMonitor",
    "known_inverters": ["ANENJI ANJ-6200W-48PL-WIFI"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "SUB": "Solar → Utility → Battery",
    "SBU": "Solar → Battery → Utility",
    "SUF": "Solar → Utility First",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "SOF": "Solar First",
    "SNU": "Solar and Utility",
    "OSO": "Only Solar",
    "SOR": "Solar or Utility",
}

# API returns lowercase "Grid mode" etc., which do not match the canonical
# OPERATING_MODES enum and cause the sensor to go unavailable. Normalise to
# the capital-Mode forms.
OPERATING_MODE_MAPPING: dict[str, str] = {
    "Grid mode": "Grid Mode",
    "Battery mode": "Battery Mode",
    "Off-grid mode": "Off-Grid Mode",
    "Hybrid mode": "Hybrid Mode",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Expose State of Charge
    "Battery SOC": "State of Charge",
    # Fix API titles with typos and double spaces
    "DCDC  module Termperature": "DC Module Temperature",
    "PV module  temperature": "PV Temperature",
    # Energy counters arrive under verbose names
    "Daily PV energy generation": "Energy Today",
    "Total PV energy generation": "Energy Total",
}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
}
