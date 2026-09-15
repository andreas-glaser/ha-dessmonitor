"""DessMonitor Data Collector (devcode 6416)."""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 6416)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["PowMr POW-HVM6.2M-48V-N"],
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

OPERATING_MODE_MAPPING: dict[str, str] = {
    "Invert Mode": "Battery",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Input Frequency": "Grid Frequency",
    "AC Input Voltage": "Grid Voltage",
    "AC Output Load": "Load Percent",
    "Battery Capacity": "State of Charge",
    "Output Source Priority": "Output priority",
    "PV total Power": "PV Total Charger Power",
    "PV1 Input Power": "PV1 Charger Power",
    "PV1 Input Voltage": "PV1 Voltage",
    "PV2 input power": "PV2 Charger Power",
    "PV2 input voltage": "PV2 Voltage",
    "Working State": "Operating mode",
}

VALUE_TRANSFORMATIONS: dict = {}

# Battery Capacity is already present in queryDeviceLastData for this collector.
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
