"""DessMonitor Data Collector (devcode 2376)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2376)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["POW-HVM6.2K-48V-LIP"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING = {
    "SBU": "Solar → Battery → Utility",
    "SUB": "Solar → Utility → Battery",
    "UTI": "Utility First",
    "SOL": "Solar First",
}

CHARGER_PRIORITY_MAPPING = {
    "Utility First": "Grid charging priority",
    "PV First": "Solar charging priority",
    "PV Is At The Same Level As Utility": "Solar and grid equal",
    "Only PV": "Solar only charging",
    "Only PV charging is allowed": "Solar only charging",
}

OPERATING_MODE_MAPPING = {
    "Power On": "Starting up",
    "Standby": "Standby mode",
    "Line": "Grid Mode",
    "Mains": "Grid Mode",
    "Mains Mode": "Grid Mode",
    "Battery": "Battery mode",
    "Fault": "Fault condition",
    "Off-Grid Mode": "Off-grid operation",
    "Grid Mode": "Grid-tied operation",
    "Hybrid Mode": "Hybrid operation",
}

SENSOR_TITLE_MAPPINGS = {
    # Fix common API typos/inconsistencies
    "INV Module Termperature": "Inverter Temperature",
    "DC Module Termperature": "DC Module Temperature",
    "Output frequency": "Output Frequency",
    # Standardize energy sensor names
    "energyToday": "Daily Energy",
    "energyTotal": "Total Energy",
    "outpower": "PV Power",
    # Add more mappings as needed for this devcode
    "PV Charge Power": "Solar Charging Power",
    "AC charging power": "Grid Charging Power",
    "Battery Power": "Battery Power",
    "Battery percentage": "State of Charge",
}

VALUE_TRANSFORMATIONS: dict = {
    # Example: Convert specific units or formats
    # "sensor_name": lambda value: transform_function(value),
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
}
