"""Eybond Data Collector (devcode 6416).

Voltronic-family inverter on the DessMonitor platform, sharing its reading
titles and its control template with devcodes 2477 and 2341: the same
spellings, the same vendor mistakes in them - "Nonimal Output Active Power",
"Beeps While Primary Source Interupt" - and the same control field ids down to
``bat_sp_floting_charging_voltage``. The shared vocabulary is in
``eybond_voltronic``; evidence is the diagnostics download in
``docs/evidence/devcodes/analysis_6416.json`` (#81).

What is this devcode's own is the second PV string. This collector reports
"PV1 Input Voltage", "PV1 Input Power", "PV2 input voltage", "PV2 input power"
and "PV total Power" where the single-string members of the family report "PV
Input Voltage" and "PV Input Power", so those five mappings are declared here
and the family's are left to the devcodes that send them.

The download also shows the option lists this collector answers with: 197
bulk-charging voltages spanning 25.0 V to 61.0 V on a device whose "Rated
Battery Voltage" reads 48.0 V. Devcodes 2477 and 2341 narrow that list to the
reported battery class with ``filter_control_options`` (#40). That is not
adopted here: it changes the options of selects an installation already
publishes, which is a deliberate change of its own, and on a device whose
payload omits the rating the filter leaves a select with no options at all.
"""

from __future__ import annotations

from .eybond_voltronic import (
    CHARGER_PRIORITY_MAPPING,
    LOCAL_CONTROL_OPTION_VALUES,
    OUTPUT_PRIORITY_MAPPING,
)
from .eybond_voltronic import SENSOR_TITLE_MAPPINGS as FAMILY_SENSOR_TITLE_MAPPINGS
from .eybond_voltronic import SETTING_READINGS

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 6416)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": ["PowMr POW-HVM6.2M-48V-N", "iSolar SMH-III 6.2 kW"],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "Invert Mode": "Battery",
}

# The family's titles, plus the two-string PV readings only this devcode sends.
SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    **FAMILY_SENSOR_TITLE_MAPPINGS,
    "PV total Power": "PV Total Charger Power",
    "PV1 Input Power": "PV1 Charger Power",
    "PV1 Input Voltage": "PV1 Voltage",
    "PV2 input power": "PV2 Charger Power",
    "PV2 input voltage": "PV2 Voltage",
}

VALUE_TRANSFORMATIONS: dict = {}

# Battery Capacity is already present in queryDeviceLastData for this collector.
PARAMETER_SENSOR_NAMES: set[str] = set()

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "setting_readings": SETTING_READINGS,
    "local_control_option_values": LOCAL_CONTROL_OPTION_VALUES,
}
