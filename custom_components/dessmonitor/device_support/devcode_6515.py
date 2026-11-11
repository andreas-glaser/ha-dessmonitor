"""Eybond Data Collector (devcode 6515)"""

from __future__ import annotations

from .eybond_ess import SETTING_READINGS

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 6515)",
    "description": "Eybond data collector/gateway for single-phase inverters (WiFi)",
    "manufacturer": "Eybond",
    "known_inverters": [
        "ANENJI ANJ-HHS-11KW-48V-WIFI",
        "Maxsky EM11000 11kW 48V",
    ],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "SUB": "Solar → Utility → Battery",
    "SBU": "Solar → Battery → Utility",
    "SUF": "Solar → Utility First",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "SOF": "Solar First",
    "SNU": "Solar and Utility",
    "OSO": "Only Solar",
    "SOR": "Solar or Utility",
}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "OffgridMode": "Off-grid Mode",
    "Bypass Mode": "Grid Mode",
    "Line Mode": "Grid Mode",
    "Mains Mode": "Grid Mode",
    "Battery Mode": "Battery Mode",
    "Inverter Mode": "Off-grid Mode",
    "Standby": "Standby",
    "Fault": "Fault",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Fix typos
    "INV Module Termperature": "Inverter Temperature",
    "DC Module Termperature": "DC Module Temperature",
    "Output Aparent Power": "Output Apparent Power",
    "Devise serial number": "Device Serial Number",
    # Standardize output sensors
    "Output frequency": "Output Frequency",
    # PV sensors
    "PV1 Current": "PV1 Charger Current",
    "PV1 Power": "PV1 Charger Power",
    "PV2 Current": "PV2 Charger Current",
    "PV2 Power": "PV2 Charger Power",
    "Total PV Power": "PV Power",
    "Total PV Charging Power": "PV Total Charger Power",
    "Total PV Charging Current": "PV Charging Current",
    "PV temperature": "PV Temperature",
    # Energy sensors
    "Daily PV energy generation": "Energy Today",
    "Total PV energy generation": "Energy Total",
    # Priority sensors
    "Main Output Priority": "Output priority",
    "Current output priority": "Output priority",
    "Current charging priority": "Charger Source Priority",
}

CONTROL_FIELD_MAPPINGS: dict[str, str] = {
    # The collector reports this setting under its internal identifier. Name it
    # after the equalization settings it sits between.
    "bat_eq_time": "Eq charging time",
}

# Cloud control ids, not local Modbus write addresses. The four schedule
# boundaries read as HH:MM, and the clock reads the same 19-character
# "YYYY-MM-DD HH:MM:SS" string as 6544's sys_eybond_read_44023, both confirmed
# by hardware reads reported for #57.
TEMPORAL_CONTROLS: dict[str, str] = {
    "bat_eybond_read_61": "time",
    "bat_eybond_read_62": "time",
    "bse_eybond_read_52": "time",
    "bse_eybond_read_53": "time",
    "sys_eybond_read_95": "text",
}


VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

# The setpoints this collector returns among the telemetry, shared with the
# other Eybond ESS collectors in ``eybond_ess``. The evidence is the Maxsky
# EM11000 report in ``docs/evidence/devcodes/analysis_6515.json``: of the 79
# titles it carries, 40 reach no sensor and every one of the 40 is spelled as a
# control field of the same device, 17 of them with a unit, which is what made
# the support report tell the owner readings were missing (#76).

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "control_field_mappings": CONTROL_FIELD_MAPPINGS,
    "temporal_controls": TEMPORAL_CONTROLS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "setting_readings": SETTING_READINGS,
}
