"""Eybond Data Collector (devcode 2376)"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2376)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
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
    "PV is at the same level as mains": "Solar and grid equal",
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
    # The summary endpoint's AC output figure, which this collector reports
    # itself in watts. Mapping it onto that reading is what keeps the merge
    # from publishing a second entity for one measurement (#75).
    "outpower": "Output Active Power",
    "Battery percentage": "State of Charge",
}

VALUE_TRANSFORMATIONS: dict = {}

# SOC is only returned by queryDeviceParsEs, not queryDeviceLastData.
PARAMETER_SENSOR_NAMES: set[str] = {"Battery percentage"}

# This collector answers the Output Voltage control with the live output
# voltage - 229.8, 230.1, 230.3 and 231.3 V across the four inverters in the
# download, against options of 220, 230 and 240 - while the setpoint it is
# asking about is reported as its own reading (#61).
CONTROL_VALUE_READINGS: dict[str, str] = {
    "bse_eybond_ctrl_64": "Output Voltage Setting",
}

# This devcode's control template has been read against the committed
# evidence, so its controls are registered enabled rather than left for the
# owner to find (#90).
#
# The committed template is 39 owner settings: battery voltages and
# currents, the two priorities, equalization, the display and the buzzer.
#
# The fields below are registered disabled instead. Each is destructive,
# irreversible or a grid-compliance setting, and none is something to change
# by accident; an owner who wants one enables it once.
CONTROLS_REVIEWED = True

PROTECTED_CONTROLS: frozenset[str] = frozenset(
    {
        # Reset User Settings
        "sys_eybond_ctrl_96",
        # Clear Record
        "sys_eybond_ctrl_95",
        # Output control, which stops the AC output
        "sys_eybond_ctrl_97",
    }
)


DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "control_value_readings": CONTROL_VALUE_READINGS,
    "controls_reviewed": CONTROLS_REVIEWED,
    "protected_controls": PROTECTED_CONTROLS,
}
