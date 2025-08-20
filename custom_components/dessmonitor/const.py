"""Constants for the DessMonitor integration."""

from typing import Final

DOMAIN: Final = "dessmonitor"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_COMPANY_KEY: Final = "company_key"
CONF_UPDATE_INTERVAL: Final = "update_interval"

DEFAULT_COMPANY_KEY: Final = "bnrl_frRFjEz8Mkn"
DEFAULT_UPDATE_INTERVAL: Final = 300  # 5 minutes
MIN_UPDATE_INTERVAL: Final = 60  # 1 minute
MAX_UPDATE_INTERVAL: Final = 3600  # 1 hour

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
}

BINARY_SENSOR_TYPES = {
    "Operating mode": {
        "name": "Operating Mode",
        "device_class": None,
        "icon": "mdi:power-settings",
    }
}

OPERATING_MODES = {
    "Off-Grid Mode": "off_grid",
    "Grid Mode": "grid",
    "Hybrid Mode": "hybrid",
}
