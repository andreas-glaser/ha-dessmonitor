"""Device support template for DessMonitor devcode XXXX.

COPY THIS FILE TO CREATE SUPPORT FOR A NEW DEVCODE:
1. Copy this file to devcode_XXXX.py (replace XXXX with your devcode number)
2. Update all the mappings below with values specific to your data collector
3. Add the import in device_registry.py
4. Test with your collector and submit a PR!

This file contains all collector-specific mappings and configurations for devcode XXXX.
The devcode represents the data collector/gateway device, not the inverter itself.
Replace XXXX with your actual devcode throughout this file.
"""

from __future__ import annotations

# Device Information
# Update this with information about your specific data collector model
DEVICE_INFO = {
    "name": "Your Data Collector Model (devcode XXXX)",
    "description": "Description of your data collector/gateway device",
    "manufacturer": "DessMonitor",  # or actual manufacturer
    "supported_features": [
        # List features your device supports - common options:
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
        # Add any collector-specific features
    ],
}

# Output Priority Mappings
# Map the actual API values your data collector returns to user-friendly descriptions
# To find these: check your collector's API response for "Output priority" sensor
OUTPUT_PRIORITY_MAPPING: dict = {
    # Example mappings - replace with your device's actual values:
    # "API_VALUE": "User Friendly Description",
    # "0": "Utility First",
    # "1": "Solar First",
    # "2": "Solar → Battery → Utility",
}

# Charger Priority Mappings
# Map the actual API values your data collector returns to user-friendly descriptions
# To find these: check your collector's API response for "Charger Source Priority" sensor
CHARGER_PRIORITY_MAPPING: dict = {
    # Example mappings - replace with your device's actual values:
    # "API_VALUE": "User Friendly Description",
    # "Utility First": "Grid charging priority",
    # "PV First": "Solar charging priority",
}

# Operating Mode Mappings
# Map the actual API values your data collector returns to user-friendly descriptions
# To find these: check your collector's API response for "Operating mode" sensor
OPERATING_MODE_MAPPING: dict = {
    # Example mappings - replace with your device's actual values:
    # "API_VALUE": "User Friendly Description",
    # "Power On": "Starting up",
    # "Standby": "Standby mode",
    # "Line": "Grid Mode",
    # "Mains Mode": "Grid Mode",  # Example: normalize synonyms to avoid enum errors
    # "Battery": "Battery mode",
}

# Sensor Title Mappings
# Map API sensor titles to cleaner, standardized display names
# This is useful for fixing typos or making names more consistent
SENSOR_TITLE_MAPPINGS: dict = {
    # Example mappings - add any sensors that need better names:
    # "API Sensor Name": "Better Display Name",
    # "INV Module Termperature": "Inverter Temperature",  # Fix typo
    # "energyToday": "Daily Energy",  # More readable
}

# Sensor Value Transformations
# Define functions to transform sensor values if needed
# This is for more complex transformations than simple mappings
VALUE_TRANSFORMATIONS: dict = {
    # Example: Convert units or apply calculations
    # "sensor_name": lambda value: float(value) * 1000,  # Convert kW to W
    # "temperature_sensor": lambda value: float(value) * 9/5 + 32,  # C to F
}

# Export all mappings in standardized structure
# DO NOT MODIFY THIS PART - just update the mappings above
DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
}
