"""Eybond Data Collector (devcode 6544)"""

from __future__ import annotations

from .eybond_ess import SETTING_READINGS

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 6544)",
    "description": "Eybond data collector/gateway for split-phase inverters",
    "manufacturer": "Eybond",
    "known_inverters": ["ANENJI ANJ-HHS-11KW-48V", "ANENJI ANJ-11KW-48V-W-P"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
        "split_phase_output",
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
    "Bypass Mode": "Grid Mode",
    "Line Mode": "Grid Mode",
    "Mains Mode": "Grid Mode",
    "Battery Mode": "Battery Mode",
    "Inverter Mode": "Off-grid Mode",
    "OffgridMode": "Off-grid Mode",
    "Standby": "Standby",
    "Fault": "Fault",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Fix typos
    "INV Module Termperature": "Inverter Temperature",
    "DC Module Termperature": "DC Module Temperature",
    "Total Output Aparent Power": "Output Apparent Power",
    "devise serial number": "Device Serial Number",
    # Standardize output sensors
    "Output frequency": "Output Frequency",
    "Total Output Active Power": "Output Active Power",
    "Total Output Current": "Output Current",
    "Total Load Percentage": "Load Percent",
    # PV sensors
    "PV1 Current": "PV1 Charger Current",
    "PV1 Power": "PV1 Charger Power",
    "PV2 Current": "PV2 Charger Current",
    "PV2 Power": "PV2 Charger Power",
    "Total PV Power": "PV Power",
    "Total PV Charging Power": "PV Total Charger Power",
    "Total PV Charging Current": "PV Charging Current",
    # Energy sensors
    "Daily PV energy generation": "Energy Today",
    "Total PV energy generation": "Energy Total",
    # Priority sensors
    "Main Output Priority": "Output priority",
    "Current output priority": "Output priority",
    "Current charging priority": "Charger Source Priority",
}

# Cloud control ids, not local Modbus write addresses. Each entry moves the
# field off the number platform, where a clock value cannot be represented.
# Verified by the hardware writes and readbacks recorded in
# docs/evidence/temporal_controls/ (#48).
TEMPORAL_CONTROLS: dict[str, str] = {
    "bat_eybond_read_43988": "time",
    "bat_eybond_read_43989": "time",
    "bse_eybond_read_43979": "time",
    "bse_eybond_read_43980": "time",
    "sys_eybond_read_44023": "text",
}


VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

# The setpoints this collector returns among the telemetry, shared with the
# other Eybond ESS collectors in ``eybond_ess``. The evidence is the three
# ANENJI ANJ-11KW-48V-W-P inverters in
# ``docs/evidence/devcodes/analysis_6544_anenji_11kw.json``: each reports an
# identical 46 titles that reach no sensor, 44 of them spelled as a control
# field of the same device and 20 of those carrying a unit, which is the
# "missing 20 readings" card its owner saw (#77). The two that are not controls
# are "Equipment type" and "Protocol Number".

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "temporal_controls": TEMPORAL_CONTROLS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "setting_readings": SETTING_READINGS,
}
