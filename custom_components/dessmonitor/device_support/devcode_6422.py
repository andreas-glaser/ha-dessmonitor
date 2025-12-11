"""DessMonitor Data Collector (devcode 6422)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 6422)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["Must PH19-6048 EXP"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "Grid-Tie": "Grid Mode",
    "OffGrid": "Off-Grid Mode",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "work state": "Operating mode",
    "Grid frequency": "Grid Frequency",
    "Inverter frequency": "Output frequency",
    "Batt Current": "Battery Current",
    "batt power": "Battery Power",
}

VALUE_TRANSFORMATIONS: dict = {}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
}
