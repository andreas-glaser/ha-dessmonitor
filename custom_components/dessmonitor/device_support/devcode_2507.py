"""DessMonitor Data Collector (devcode 2507)

Confirmed with ANENJI ANJ-6200W-48PL-WIFI.

The collector exposes all runtime values (including Battery SOC) via the
primary queryDeviceLastData endpoint, so no extra parameters fetch is
needed.  Mappings below cover the fields whose API titles do not match the
plugin's canonical sensor names even after case-insensitive lookup —
notably "Battery SOC", energy totals, and temperature titles with typos
or double spaces.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode 2507)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["ANENJI ANJ-6200W-48PL-WIFI"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

# Output source priority (value of "Current output priority" sensor).
# API returns the short code, e.g. "SUB".
OUTPUT_PRIORITY_MAPPING = {
    "SBU": "Solar → Battery → Utility",
    "SUB": "Solar → Utility → Battery",
    "UTI": "Utility First",
    "SOL": "Solar First",
}

# Charger source priority (value of "Current charging priority" sensor).
# API returns the short code, e.g. "SOF".
CHARGER_PRIORITY_MAPPING = {
    "CSO": "Solar only charging",
    "SNU": "Solar and grid equal",
    "CUB": "Grid charging priority",
    "OSO": "Solar only charging",
    "SOF": "Solar first",
    # Legacy long-form values from other devcodes (kept for safety)
    "Utility First": "Grid charging priority",
    "PV First": "Solar charging priority",
    "PV Is At The Same Level As Utility": "Solar and grid equal",
    "Only PV": "Solar only charging",
    "Only PV charging is allowed": "Solar only charging",
}

# Operating mode normalisation.
# The Anenji collector returns values like "Grid mode" (lower-case m),
# but the Home Assistant enum sensor only accepts canonical values from
# const.OPERATING_MODES such as "Grid Mode".  Without this mapping the
# Operating Mode sensor reports "unavailable".
OPERATING_MODE_MAPPING = {
    "Grid mode": "Grid Mode",
    "Battery mode": "Battery mode",
    "Off-grid mode": "Off-Grid Mode",
    "Hybrid mode": "Hybrid Mode",
    "Line": "Grid Mode",
    "Mains": "Grid Mode",
    "Mains Mode": "Grid Mode",
    "Battery": "Battery mode",
    "Power On": "Starting up",
    "Standby": "Standby mode",
    "Fault": "Fault condition",
}

# Sensor title remapping.  Only fields that do NOT match a canonical
# const.SENSOR_TYPES key even after case-insensitive/whitespace normalisation
# are listed here.  Most basic sensors (Grid Voltage/Power/Frequency,
# Output *, Battery Voltage/Current/Power, PV Voltage/Current/Power,
# Load Percent) already resolve automatically.
SENSOR_TITLE_MAPPINGS = {
    # Critical: expose State of Charge
    "Battery SOC": "State of Charge",
    # Fix API temperature titles with typos/double spaces
    "DCDC  module Termperature": "DC Module Termperature",
    "PV module  temperature": "PV Temperature",
    # Energy counters arrive under verbose names — normalise to plugin keys
    "Daily PV energy generation": "Energy Today",
    "Total PV energy generation": "Energy Total",
}

VALUE_TRANSFORMATIONS: dict = {}

# SOC is delivered via queryDeviceLastData, no extra parameter fetch needed.
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
