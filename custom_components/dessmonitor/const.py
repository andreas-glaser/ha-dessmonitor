"""Constants for the DessMonitor integration."""

from typing import Final

DOMAIN: Final = "dessmonitor"
VERSION: Final = "1.8.0"

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

API_BASE_URL: Final = "https://api.dessmonitor.com/public/"

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
    "Battery Charging Current": {
        "name": "Battery Charging Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:battery-charging",
    },
    "Battery Discharge Current": {
        "name": "Battery Discharge Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:battery-arrow-down",
    },
    "Batt Current": {
        "name": "Battery Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "Inverter Current": {
        "name": "Inverter Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-dc",
    },
    "BMS battery current": {
        "name": "BMS Battery Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:battery",
    },
    "BMS battery voltage": {
        "name": "BMS Battery Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
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
    "PV1 Charger Current": {
        "name": "PV1 Charger Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-dc",
    },
    "PV2 Charger Current": {
        "name": "PV2 Charger Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-dc",
    },
    "grid current": {
        "name": "Grid Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "load current": {
        "name": "Load Current",
        "unit": UNITS["CURRENT"],
        "device_class": "current",
        "state_class": "measurement",
        "icon": "mdi:current-ac",
    },
    "Output frequency": {
        "name": "Output Frequency",
        "unit": UNITS["FREQUENCY"],
        "device_class": "frequency",
        "state_class": "measurement",
        "icon": "mdi:sine-wave",
    },
    "Output Frequency": {
        "name": "Output Frequency",
        "unit": UNITS["FREQUENCY"],
        "device_class": "frequency",
        "state_class": "measurement",
        "icon": "mdi:sine-wave",
    },
    "Inverter frequency": {
        "name": "Inverter Frequency",
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
    "Grid frequency": {
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
    "SOC": {
        "name": "State of Charge",
        "unit": UNITS["PERCENTAGE"],
        "state_class": "measurement",
        "icon": "mdi:battery-high",
    },
    "State of Charge": {
        "name": "State of Charge",
        "unit": UNITS["PERCENTAGE"],
        "state_class": "measurement",
        "icon": "mdi:battery-high",
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
    "AC radiator temperature": {
        "name": "AC Radiator Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "DC radiator temperature": {
        "name": "DC Radiator Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "PV Radiator Temperature": {
        "name": "PV Radiator Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "Inverter Heat Sink Temperature": {
        "name": "Inverter Heat Sink Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "Inverter Radiator Temperature": {
        "name": "Inverter Radiator Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "Transformer temperature": {
        "name": "Transformer Temperature",
        "unit": UNITS["TEMPERATURE"],
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    "BMS battery temperature": {
        "name": "BMS Battery Temperature",
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
    "work state": {
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
    "Inverter Voltage": {
        "name": "Inverter Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "PV Voltage": {
        "name": "Solar Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "PV1 Voltage": {
        "name": "PV1 Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "PV2 Voltage": {
        "name": "PV2 Voltage",
        "unit": UNITS["VOLTAGE"],
        "device_class": "voltage",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
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
    "Load Apparent Power": {
        "name": "Load Apparent Power",
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
    "PV Total Charger Power": {
        "name": "PV Total Charger Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "PV1 Charger Power": {
        "name": "PV1 Charger Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "PV2 Charger Power": {
        "name": "PV2 Charger Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:solar-power",
    },
    "PGrid": {
        "name": "Grid Active Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:transmission-tower",
    },
    "PLoad": {
        "name": "Load Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "PInverter": {
        "name": "Inverter Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:flash",
    },
    "batt power": {
        "name": "Battery Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:battery",
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
    "Energy Today": {
        "name": "Energy Today",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:solar-power",
    },
    "Energy Total": {
        "name": "Energy Total",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:solar-power",
    },
    "Battery Energy Today (Charge)": {
        "name": "Battery Energy Today (Charge)",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:battery-plus",
    },
    "Battery Energy Today (Discharge)": {
        "name": "Battery Energy Today (Discharge)",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:battery-minus",
    },
    "Battery Energy Total (Charge)": {
        "name": "Battery Energy Total (Charge)",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        # Devices such as SRNE SR-EOV24 report occasional decreases,
        # so treat as measurement to avoid HA Recorder warnings (issue #3).
        "state_class": "measurement",
        "icon": "mdi:battery-plus",
    },
    "Battery Energy Total (Discharge)": {
        "name": "Battery Energy Total (Discharge)",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "measurement",
        "icon": "mdi:battery-minus",
    },
    "PV Cumulative Power Generation": {
        "name": "PV Cumulative Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:solar-power",
    },
    "Accumulated Load Power": {
        "name": "Accumulated Load Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:home-lightning-bolt",
    },
    "Accumulated Mains Load Energy": {
        "name": "Accumulated Mains Load Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:transmission-tower-import",
    },
    "Accumulated Self_Use Power": {
        "name": "Accumulated Self-Use Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:solar-power",
    },
    "Accumulated Sell Power": {
        "name": "Accumulated Sell Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:transmission-tower-export",
    },
    "accumulated buy power": {
        "name": "Accumulated Buy Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:transmission-tower-import",
    },
    "accumulated charger power": {
        "name": "Accumulated Charge Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:battery-charging",
    },
    "accumulated discharger power": {
        "name": "Accumulated Discharge Energy",
        "unit": UNITS["ENERGY"],
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:battery-arrow-down",
    },
    "Accumulated Battery Charge Ah": {
        "name": "Accumulated Battery Charge Ah",
        "unit": "Ah",
        "state_class": "total_increasing",
        "icon": "mdi:battery-plus",
    },
    "Accumulated Battery Discharge Ah": {
        "name": "Accumulated Battery Discharge Ah",
        "unit": "Ah",
        "state_class": "total_increasing",
        "icon": "mdi:battery-minus",
    },
    "Daily Battery Charge Ah": {
        "name": "Daily Battery Charge Ah",
        "unit": "Ah",
        "state_class": "total_increasing",
        "icon": "mdi:battery-plus",
    },
    "Daily Battery Discharge Ah": {
        "name": "Daily Battery Discharge Ah",
        "unit": "Ah",
        "state_class": "total_increasing",
        "icon": "mdi:battery-minus",
    },
    "Software version": {
        "name": "Software Version",
        "unit": "",
        "icon": "mdi:chip",
        "entity_category": "diagnostic",
    },
    "rated power": {
        "name": "Rated Power",
        "unit": UNITS["POWER"],
        "device_class": "power",
        "state_class": "measurement",
        "icon": "mdi:flash",
        "entity_category": "diagnostic",
    },
    "charger work enable": {
        "name": "Charger Work Enable",
        "unit": "",
        "device_class": "enum",
        "options": ["ON", "OFF"],
        "icon": "mdi:toggle-switch",
        "entity_category": "diagnostic",
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

# Binary sensor types from API data points
# Currently empty but structure is in place for future binary sensors
BINARY_SENSOR_TYPES: dict = {}

# Reserved for future diagnostic sensor types
# Not currently used but maintained for future expansion
DIAGNOSTIC_SENSOR_TYPES: dict = {}
