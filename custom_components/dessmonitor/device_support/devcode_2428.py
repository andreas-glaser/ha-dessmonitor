"""DessMonitor Data Collector (devcode 2428)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2428)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["Hybrid inverter"],
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
    "AC output active power": "Output Active Power",
    "AC output frequency": "Output Frequency",
    "AC output voltage": "Output Voltage",
    "Battery capacity": "State of Charge",
    "Battery charging current": "Battery Charging Current",
    "Battery discharge current": "Battery Discharge Current",
    "Battery voltage": "Battery Voltage",
    "Grid voltage": "Grid Voltage",
    "Output load percent": "Load Percent",
    "PV Charging power": "PV Charge Power",
    "PV Input current for battery": "PV Charging Current",
    "PV Input voltage": "PV Voltage",
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
