"""DessMonitor Data Collector (devcode 6515)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 6515)",
    "description": "DessMonitor data collector/gateway for single-phase inverters (WiFi)",
    "manufacturer": "DessMonitor",
    "known_inverters": ["ANENJI ANJ-HHS-11KW-48V-WIFI"],
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

OPERATING_MODE_MAPPING: dict[str, str] = {
    "OffgridMode": "Off-grid Mode",
    "Bypass Mode": "Grid Mode",
    "Line Mode": "Grid Mode",
    "Mains Mode": "Grid Mode",
    "Battery Mode": "Battery Mode",
    "Inverter Mode": "Off-grid Mode",
    "Standby": "Standby",
    "Fault": "Fault",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Fix typos
    "INV Module Termperature": "Inverter Temperature",
    "DC Module Termperature": "DC Module Temperature",
    "Output Aparent Power": "Output Apparent Power",
    "Devise serial number": "Device Serial Number",
    # Standardize output sensors
    "Output frequency": "Output Frequency",
    # PV sensors
    "PV1 Current": "PV1 Charger Current",
    "PV1 Power": "PV1 Charger Power",
    "PV2 Current": "PV2 Charger Current",
    "PV2 Power": "PV2 Charger Power",
    "Total PV Power": "PV Power",
    "Total PV Charging Power": "PV Total Charger Power",
    "Total PV Charging Current": "PV Charging Current",
    "PV temperature": "PV Temperature",
    # Energy sensors
    "Daily PV energy generation": "Energy Today",
    "Total PV energy generation": "Energy Total",
    # Priority sensors
    "Main Output Priority": "Output priority",
    "Current output priority": "Output priority",
    "Current charging priority": "Charger Source Priority",
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
