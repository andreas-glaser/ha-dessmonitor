"""DessMonitor Data Collector (devcode 2452)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2452)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["Axpert (PI18 protocol, rebranded)"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "Solar-Utility-Battery": "Solar → Utility → Battery",
    "Solar-Battery-Utility": "Solar → Battery → Utility",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "Solar first": "PV First",
    "Solar and Utility": "PV Is At The Same Level As Utility",
    "Only solar": "Only PV",
}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Output Frequency": "Output Frequency",
    "AC output active power": "Output Active Power",
    "AC output apparent power": "Output Apparent Power",
    "AC output voltage": "Output Voltage",
    "Battery Capacity": "State of Charge",
    "Battery Discharging Current": "Battery Discharge Current",
    "Grid voltage": "Grid Voltage",
    "Output load percent": "Load Percent",
    "PV1 Input Power": "PV1 Charger Power",
    "PV1 Input voltage": "PV1 Voltage",
    "PV2 Input Power": "PV2 Charger Power",
    "Today generation": "Energy Today",
    "Total generation": "Energy Total",
    "Month generation": "Energy Month",
    "Year generation": "Energy Year",
    "Second AC output frequency": "Second Output Frequency",
    "Second AC output voltage": "Second Output Voltage",
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
