"""Constants for the DessMonitor integration."""

from typing import Final

DOMAIN: Final = "dessmonitor"
VERSION: Final = "1.3.0"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_COMPANY_KEY: Final = "company_key"
CONF_UPDATE_INTERVAL: Final = "update_interval"

DEFAULT_COMPANY_KEY: Final = "bnrl_frRFjEz8Mkn"
DEFAULT_UPDATE_INTERVAL: Final = 300
MIN_UPDATE_INTERVAL: Final = 60
MAX_UPDATE_INTERVAL: Final = 3600

UPDATE_INTERVAL_OPTIONS: Final = {
    60: "1 minute (Premium)",
    300: "5 minutes (Standard)",
    600: "10 minutes",
    1800: "30 minutes",
    3600: "1 hour",
}

API_BASE_URL: Final = "http://api.dessmonitor.com/public/"

POWER_UNIT: Final = "W"
ENERGY_UNIT: Final = "kWh"
VOLTAGE_UNIT: Final = "V"
CURRENT_UNIT: Final = "A"
FREQUENCY_UNIT: Final = "Hz"
TEMPERATURE_UNIT: Final = "°C"
PERCENTAGE_UNIT: Final = "%"

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
        "unit": POWER_UNIT,
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "Battery Power": {
        "name": "Battery Power",
        "unit": POWER_UNIT,
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "PV Power": {
        "name": "Solar Power",
        "unit": POWER_UNIT,
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "Grid Power": {
        "name": "Grid Power",
        "unit": POWER_UNIT,
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:transmission-tower",
    },
    "Output Voltage": {
        "name": "Output Voltage",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "Battery Voltage": {
        "name": "Battery Voltage",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "PV Voltage": {
        "name": "Solar Voltage",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "Output Current": {
        "name": "Output Current",
        "unit": CURRENT_UNIT,
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "Battery Current": {
        "name": "Battery Current",
        "unit": CURRENT_UNIT,
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "PV Current": {
        "name": "Solar Current",
        "unit": CURRENT_UNIT,
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "Output frequency": {
        "name": "Output Frequency",
        "unit": FREQUENCY_UNIT,
        "device_class": "frequency",
        "state_class": "measurement",
        "icon": "mdi:sine-wave",
    },
    "Grid Frequency": {
        "name": "Grid Frequency",
        "unit": FREQUENCY_UNIT,
        "device_class": "frequency",
        "state_class": "measurement",
        "icon": "mdi:sine-wave",
    },
    "Load Percent": {
        "name": "Load Percentage",
        "unit": PERCENTAGE_UNIT,
        "state_class": "measurement",
        "icon": "mdi:gauge",
    },
    "INV Module Termperature": {
        "name": "Inverter Temperature",
        "unit": TEMPERATURE_UNIT,
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "DC Module Termperature": {
        "name": "DC Module Temperature",
        "unit": TEMPERATURE_UNIT,
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
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:transmission-tower",
    },
    "AC charging power": {
        "name": "AC Charging Power",
        "unit": POWER_UNIT,
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:battery-charging",
    },
    "Output Apparent Power": {
        "name": "Output Apparent Power",
        "unit": "VA",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "PV Charge Power": {
        "name": "PV Charge Power",
        "unit": POWER_UNIT,
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "AC charging current": {
        "name": "AC Charging Current",
        "unit": CURRENT_UNIT,
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "PV charging current": {
        "name": "PV Charging Current",
        "unit": CURRENT_UNIT,
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "Output Voltage Setting": {
        "name": "Output Voltage Setting",
        "unit": VOLTAGE_UNIT,
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:cog",
    },
    "outpower": {
        "name": "Total PV Power",
        "unit": "kW",
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "energyToday": {
        "name": "Energy Today",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:flash",
    },
    "energyTotal": {
        "name": "Energy Total",
        "unit": "kWh",
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

BINARY_SENSOR_TYPES = {}

DIAGNOSTIC_SENSOR_TYPES = {}
