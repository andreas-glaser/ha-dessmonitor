"""DessMonitor Data Collector (devcode 2361)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2361)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["SRNE SR-EOV24-3.5K-5KWh"],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "energy_tracking",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "Mains operation": "Grid Mode",
    "Battery operation": "Battery Mode",
    "Inverting operation": "Off-grid Mode",
    "PV operation": "Solar Mode",
    "Standby": "Standby",
    "Fault": "Fault",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "Battery level SOC": "State of Charge",
    "Current state of machine": "Operating Mode",
    "BatTypeSet": "Battery Type",
    "InvCurr": "Inverter Current",
    "Load active power": "Load Power",
    "Apparent power of load": "Load Apparent Power",
    "Load rate": "Load Percentage",
    "PV charging power": "Solar Charging Power",
    "PV charging current": "Solar Charging Current",
    "PV voltage": "PV Voltage",
    "PV radiator temperature": "PV Radiator Temperature",
    "Temperature of inverter heat sink": "Inverter Heat Sink Temperature",
    "Inverter radiator temperature": "Inverter Radiator Temperature",
    "Charging power": "Grid Charging Power",
    "battery energy today charge": "Battery Energy Today (Charge)",
    "battery energy today discharge": "Battery Energy Today (Discharge)",
    "battery energy total charge": "Battery Energy Total (Charge)",
    "battery energy total discharge": "Battery Energy Total (Discharge)",
    "Accumulated power consumption of load": "Accumulated Load Energy",
    "Accumulated load from mains consumption": "Accumulated Mains Load Energy",
    "Accumulated battery charging ampere hours": "Accumulated Battery Charge Ah",
    "Accumulated discharge ampere hours of battery": "Accumulated Battery Discharge Ah",
    "Ampere-hours of battery charging on the same day": "Daily Battery Charge Ah",
    "Ampere-hours of battery discharge on the same day": "Daily Battery Discharge Ah",
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
