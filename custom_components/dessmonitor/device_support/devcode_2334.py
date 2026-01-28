"""DessMonitor Data Collector (devcode 2334)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2334)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["EASUN 6.2KW Hybrid Solar Inverter"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "Utility first": "Utility First",
    "Solar first": "Solar First",
    "SBU first": "Solar → Battery → Utility",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "Line Mode": "Grid Mode",
    "Mains Mode": "Grid Mode",
    "Battery Mode": "Battery Mode",
    "Standby": "Standby",
    "Fault": "Fault",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC output active power": "Output Active Power",
    "AC output frequency": "Output Frequency",
    "AC output voltage": "Output Voltage",
    "Battery capacity": "State of Charge",
    "Battery charging current": "Battery Charging Current",
    "Battery discharge current": "Battery Discharge Current",
    "Battery voltage": "Battery Voltage",
    "Grid frequency": "Grid Frequency",
    "Grid voltage": "Grid Voltage",
    "Output load percent": "Load Percent",
    "PV Charging power": "PV1 Charger Power",
    "PV Input current for battery": "PV1 Charger Current",
    "PV Input voltage": "PV1 Voltage",
    "PV2 Charging power": "PV2 Charger Power",
    "PV2 Input current": "PV2 Charger Current",
    "PV2 Input voltage": "PV2 Voltage",
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
