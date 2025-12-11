"""DessMonitor Data Collector (devcode 2451)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2451)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["Axpert MKS IV 5600VA"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "Utility Solar Bat": "Utility → Solar → Battery",
    "Solar Utility Bat": "Solar → Utility → Battery",
    "Solar Bat Utility": "Solar → Battery → Utility",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "Utility First": "Utility First",
    "Solar First": "PV First",
    "Solar + Utility": "PV Is At The Same Level As Utility",
    "Only Solar Charging Permitted": "Only PV",
}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Output Active Power": "Output Active Power",
    "AC1 Output Apparent Power": "Output Apparent Power",
    "AC1 Output Frequency": "Output frequency",
    "AC1 Output Voltage": "Output Voltage",
    "Battery Capacity": "State of Charge",
    "Output Load Percent": "Load Percent",
    "Output Source Priority": "Output priority",
    "PV1 Charging Power": "PV1 Charger Power",
    "PV1 Input Current": "PV1 Charger Current",
    "PV1 Input Voltage": "PV1 Voltage",
    "PV2 Charging power": "PV2 Charger Power",
    "PV2 Input current": "PV2 Charger Current",
    "PV2 Input voltage": "PV2 Voltage",
    "Solar Feed To Grid Power": "Grid Power",
    "Today generation": "Energy Today",
    "Total generation": "Energy Total",
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
