"""Eybond Data Collector (devcode 6514)."""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 6514)",
    "description": "Eybond data collector/gateway for dual-output inverters",
    "manufacturer": "Eybond",
    "known_inverters": [
        "ANENJI 5KW 48V Hybrid Solar Inverter",
        "Aninerel 6.2KW 48V",
        "Aninerel 4.2KW 24V (firmware 8.50.18.3, external Wi-Fi module)",
        "ANENJI 4.2KW 24V",
    ],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "parameter_control",
        "split_phase_output",
    ],
}

# Codes from the API control enums bse_eybond_read_55 and bat_eybond_read_74.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "UTI": "Utility First",
    "SOL": "Solar First",
    "SBU": "Solar → Battery → Utility",
    "SUB": "Solar → Utility → Battery",
    "SUF": "Solar → Utility First",
}

# "CSO" is the third code this collector offers and is left unlabelled: its
# meaning is not established by the API, the manual, or an observed reading, and
# a wrong charge-source label would be worse than the raw code.
CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "SNU": "Solar and Utility",
    "OSO": "Only Solar",
    # The vendor manual for the Aninerel 4.2KW 24V names CSO solar-first
    # charging: solar charges as priority and utility only steps in when solar
    # is unavailable (#56).
    "CSO": "Solar First",
}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "OffgridMode": "Off-grid Mode",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Fix typos
    "Total Output Aparent Power": "Output Apparent Power",
    "Output L1 Aparent Power": "Output L1 Apparent Power",
    "Output L2 Aparent Power": "Output L2 Apparent Power",
    # This collector reports only per-leg and summed output, no single "Output" set
    "Total Output Active Power": "Output Active Power",
    "Total Output Current": "Output Current",
    "Total Load Percentage": "Load Percent",
    # PV sensors
    "PV Charging Power": "PV Charge Power",
    # Firmware 8.50.12.3 reports SOC under this name
    "Battery percentage": "State of Charge",
}

VALUE_TRANSFORMATIONS: dict = {}

# Firmware 8.50.12.3 reports SOC as bt_battery_capacity in queryDeviceParsEs.
# The coordinator selects parameters by their API name, not their ID.
PARAMETER_SENSOR_NAMES: set[str] = {"Battery percentage"}

# Setpoints this collector returns among the telemetry. Every one is spelled
# exactly as a control field on the same device, and carries the value that
# control reads back, so each already reaches Home Assistant as a number or
# select entity, or, for "Output mode", is a control with a single option and
# nothing to choose. A sensor for them would be a second entity for one
# setting. The evidence is the ANENJI 4.2KW 24V diagnostics download in
# ``docs/evidence/devcodes/analysis_6514_anenji_4200.json``: of its 76 counted
# titles 38 resolved, and the support report told the owner twenty readings
# were missing when every one of the twenty was a setting. The earlier CLI
# analysis recorded a unit for its first twenty samples only, which is why the
# coverage guard never saw them.
#
# "Equipment type" and "Protocol Number" are left out on purpose: they describe
# the hardware rather than configure it, carry no unit, and are not controls.
# "Output Voltage Setting" is not listed either: it already resolves to its own
# sensor, which an installation publishes today and must keep.
SETTING_READINGS: set[str] = {
    # Battery charging and protection setpoints, published as number entities.
    "Battery overvoltage protection point",
    "Maximum charging voltage",
    "Floating charge voltage",
    "Mains mode battery discharge recovery point",
    "Mains mode battery low voltage protection point",
    "Off-grid mode battery low voltage protection point",
    "Off-grid mode OP1 battery low voltage protection point",
    "Constant pressure to float waiting time",
    "Maximum charging current",
    "Maximum mains charging current",
    "Maximum discharge current protection",
    "Low DC Protection SOC In AC Mode",
    "Low DC Recovery SOC In AC Mode",
    # The vendor pads this title with two spaces; titles compare collapsed.
    "SOC Protection value of OP1 In off-grid mode",
    "Battery Low Cut Off SOC",
    "OP2 overload alarm setting",
    # Equalization setpoints. "bat_eq_time" is the vendor's own title.
    "Eq charging voltage",
    "bat_eq_time",
    "Eq timeout exit",
    "Eq charging interval",
    # Mode and behaviour settings, published as select entities.
    "Battery Type",
    "Battery Eq mode enable",
    "Buzzer Mode",
    "LCD backlight",
    "LCD automatically returns to the homepage",
    "Input Mode",
    "Output mode",
    "Output Frequency Setting",
    "Overload automatic restart",
    "Automatic restart when over temperature",
    "Overload transfer to bypass enable",
    "Automatic mains output enable",
    "Automatic activation for lithium battery",
    "Whether the OP2 allows the output",
    "Boot method",
    "Remote switch",
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "setting_readings": SETTING_READINGS,
}
