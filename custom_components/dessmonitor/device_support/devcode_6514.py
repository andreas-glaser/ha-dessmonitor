"""DessMonitor Data Collector (devcode 6514)."""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 6514)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["ANENJI 5KW 48V Hybrid Solar Inverter"],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
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
