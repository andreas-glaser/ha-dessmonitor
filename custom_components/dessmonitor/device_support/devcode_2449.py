"""Eybond Data Collector (devcode 2449)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2449)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": ["EASUN 8KWA", "EASUN 11KWA", "WKS Evo MAX II 10kVA 48V"],
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
    "Solar First": "PV First",
    "Solar + Utility": "PV Is At The Same Level As Utility",
    "Only Solar Charging Permitted": "Only PV",
}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "Mains operation": "Grid Mode",
    "Line Mode": "Grid Mode",
    "Battery operation": "Battery Mode",
    "Inverting operation": "Off-grid Mode",
    "Inverter Operation": "Off-grid Mode",
    "Inverter operation": "Off-grid Mode",
    "PV operation": "Solar Mode",
    "Standby": "Standby",
    "Inverter Fault": "Fault",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Output Active Power": "Output Active Power",
    "AC Output Apparent Power": "Output Apparent Power",
    "AC Output Frequency": "Output Frequency",
    "AC Output Voltage": "Output Voltage",
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

# This collector reports both generation counters in watt-hours while the
# sensors publish kilowatt-hours, so two AXPERT MAX II 10 kW inverters showed
# 8466 kWh generated today and 15045200 kWh in their lifetime (#71). The
# collector labels both readings "Wh" and the registry scales from that label;
# these entries only state what the download showed, for a payload that sends
# the value without the unit. Unlike devcode 2452, whose lifetime total is
# already in kWh, both of this one's are in Wh.
SOURCE_UNITS: dict[str, str] = {
    "Energy Today": "Wh",
    "Energy Total": "Wh",
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "source_units": SOURCE_UNITS,
}
