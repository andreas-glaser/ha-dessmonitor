"""Constants for the DessMonitor integration."""

from typing import Final

DOMAIN: Final = "dessmonitor"
VERSION: Final = "1.4.1"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_COMPANY_KEY: Final = "company_key"
CONF_UPDATE_INTERVAL: Final = "update_interval"

DEFAULT_COMPANY_KEY: Final = "bnrl_frRFjEz8Mkn"
DEFAULT_UPDATE_INTERVAL: Final = 300
MIN_UPDATE_INTERVAL: Final = 60
MAX_UPDATE_INTERVAL: Final = 3600

UPDATE_INTERVAL_OPTIONS: Final = {
    60: "1 minute (Collection Acceleration)",
    300: "5 minutes (Standard)",
    600: "10 minutes (Reduced API usage)",
    1800: "30 minutes (Low usage)",
    3600: "1 hour (Minimal usage)",
}

API_BASE_URL: Final = "http://api.dessmonitor.com/public/"

UNITS: Final = {
    "POWER": "W",
    "POWER_KW": "kW",
    "APPARENT_POWER": "VA",
    "ENERGY": "kWh",
    "VOLTAGE": "V",
    "CURRENT": "A",
    "FREQUENCY": "Hz",
    "TEMPERATURE": "°C",
    "PERCENTAGE": "%",
}

OUTPUT_PRIORITIES = [
    "SBU",
    "SUB",
    "UTI",
    "SOL",
]

CHARGER_PRIORITIES = [
    "Utility First",
    "PV First",
    "PV Is At The Same Level As Utility",
    "Only PV",
    "Only PV charging is allowed",
]

BATTERY_TYPES = ["AGM", "FLD", "USER", "Li1", "Li2", "Li3", "Li4"]

OPERATING_MODES = [
    "Power On",
    "Standby",
    "Line",
    "Battery",
    "Fault",
    "Shutdown Approaching",
    "Off-Grid Mode",
    "Grid Mode",
    "Hybrid Mode",
    "Unknown",
]

# Dynamic operating modes - automatically populated from devcode mappings
# This list is extended at runtime with transformed values


SENSOR_TYPES = {
    "Output Active Power": {
        "name": "Output Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "Battery Power": {
        "name": "Battery Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "PV Power": {
        "name": "Solar Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "Grid Power": {
        "name": "Grid Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:transmission-tower",
    },
    "Output Voltage": {
        "name": "Output Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "Battery Voltage": {
        "name": "Battery Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "PV Voltage": {
        "name": "Solar Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "Output Current": {
        "name": "Output Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "Battery Current": {
        "name": "Battery Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "PV Current": {
        "name": "Solar Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "Output frequency": {
        "name": "Output Frequency",
        "unit": UNITS["FREQUENCY"],
        "device_class": "frequency",
        "state_class": "measurement",
        "icon": "mdi:sine-wave",
    },
    "Grid Frequency": {
        "name": "Grid Frequency",
        "unit": UNITS["FREQUENCY"],
        "device_class": "frequency",
        "state_class": "measurement",
        "icon": "mdi:sine-wave",
    },
    "Load Percent": {
        "name": "Load Percentage",
        "unit": UNITS["PERCENTAGE"],
        "state_class": "measurement",
        "icon": "mdi:gauge",
    },
    "INV Module Termperature": {
        "name": "Inverter Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "DC Module Termperature": {
        "name": "DC Module Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "Operating mode": {
        "name": "Operating Mode",
        "unit": "",
        "device_class": "enum",
        "icon": "mdi:power-settings",
    },
    "Grid Voltage": {
        "name": "Grid Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:transmission-tower",
    },
    "AC charging power": {
        "name": "AC Charging Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:battery-charging",
    },
    "Output Apparent Power": {
        "name": "Output Apparent Power",
        "unit": UNITS["APPARENT_POWER"],
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "PV Charge Power": {
        "name": "PV Charge Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "AC charging current": {
        "name": "AC Charging Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "PV charging current": {
        "name": "PV Charging Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "Output Voltage Setting": {
        "name": "Output Voltage Setting",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:cog",
    },
    "outpower": {
        "name": "Total PV Power",
        "unit": UNITS["POWER_KW"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "energyToday": {
        "name": "Energy Today",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:flash",
    },
    "energyTotal": {
        "name": "Energy Total",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:flash",
    },
    "Output priority": {
        "name": "Output Priority",
        "unit": "",
        "device_class": "enum",
        "options": OUTPUT_PRIORITIES,
        "icon": "mdi:electric-switch",
        "entity_category": "diagnostic",
    },
    "Charger Source Priority": {
        "name": "Charger Source Priority",
        "unit": "",
        "device_class": "enum",
        "options": CHARGER_PRIORITIES,
        "icon": "mdi:battery-charging",
        "entity_category": "diagnostic",
    },
}

BINARY_SENSOR_TYPES: dict = {}

DIAGNOSTIC_SENSOR_TYPES: dict = {}
