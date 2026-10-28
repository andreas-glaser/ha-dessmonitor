"""DessMonitor Data Collector (devcode 6514)."""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 6514)",
    "description": "DessMonitor data collector/gateway for dual-output inverters",
    "manufacturer": "DessMonitor",
    "known_inverters": [
        "ANENJI 5KW 48V Hybrid Solar Inverter",
        "Aninerel 6.2KW 48V",
    ],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "parameter_control",
        "split_phase_output",
    ],
}

# Codes from the API control enums bse_eybond_read_55 and bat_eybond_read_74.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "UTI": "Utility First",
    "SOL": "Solar First",
    "SBU": "Solar → Battery → Utility",
    "SUB": "Solar → Utility → Battery",
    "SUF": "Solar → Utility First",
}

# "CSO" is the third code this collector offers and is left unlabelled: its
# meaning is not established by the API, the manual, or an observed reading, and
# a wrong charge-source label would be worse than the raw code.
CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "SNU": "Solar and Utility",
    "OSO": "Only Solar",
}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "OffgridMode": "Off-grid Mode",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Fix typos
    "Total Output Aparent Power": "Output Apparent Power",
    "Output L1 Aparent Power": "Output L1 Apparent Power",
    "Output L2 Aparent Power": "Output L2 Apparent Power",
    # This collector reports only per-leg and summed output, no single "Output" set
    "Total Output Active Power": "Output Active Power",
    "Total Output Current": "Output Current",
    "Total Load Percentage": "Load Percent",
    # PV sensors
    "PV Charging Power": "PV Charge Power",
    # Firmware 8.50.12.3 reports SOC under this name
    "Battery percentage": "State of Charge",
}

VALUE_TRANSFORMATIONS: dict = {}

# Firmware 8.50.12.3 reports SOC as bt_battery_capacity in queryDeviceParsEs.
# The coordinator selects parameters by their API name, not their ID.
PARAMETER_SENSOR_NAMES: set[str] = {"Battery percentage"}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
}
