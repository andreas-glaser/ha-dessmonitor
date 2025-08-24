"""Device support for DessMonitor devcode 2376 - Standard Data Collector.

This file contains all collector-specific mappings and configurations for devcode 2376.
The devcode represents the data collector/gateway device that communicates with inverters.
Users can copy this file as a template to add support for other devcodes.
"""

from __future__ import annotations

# Device Information
DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2376)",
    "description": "Standard DessMonitor data collector/gateway device",
    "manufacturer": "DessMonitor",
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

# Output Priority Mappings
# Maps API values to user-friendly descriptions
OUTPUT_PRIORITY_MAPPING = {
    "SBU": "Solar → Battery → Utility",
    "SUB": "Solar → Utility → Battery",
    "UTI": "Utility First",
    "SOL": "Solar First",
}

# Charger Priority Mappings
# Maps API values to user-friendly descriptions
CHARGER_PRIORITY_MAPPING = {
    "Utility First": "Grid charging priority",
    "PV First": "Solar charging priority",
    "PV Is At The Same Level As Utility": "Solar and grid equal",
    "Only PV": "Solar only charging",
    "Only PV charging is allowed": "Solar only charging",
}

# Operating Mode Mappings
# Maps API values to user-friendly descriptions
OPERATING_MODE_MAPPING = {
    "Power On": "Starting up",
    "Standby": "Standby mode",
    "Line": "Grid mode",
    "Battery": "Battery mode",
    "Fault": "Fault condition",
    "Off-Grid Mode": "Off-grid operation",
    "Grid Mode": "Grid-tied operation",
    "Hybrid Mode": "Hybrid operation",
}

# Sensor Title Mappings
# Maps API sensor titles to standardized display names
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
}

# Sensor Value Transformations
# Define any special value transformations needed for this devcode
VALUE_TRANSFORMATIONS = {
    # Example: Convert specific units or formats
    # "sensor_name": lambda value: transform_function(value),
}

# Export all mappings in a standardized structure
DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
}
