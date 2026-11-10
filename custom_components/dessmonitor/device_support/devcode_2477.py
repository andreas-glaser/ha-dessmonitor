"""Eybond Data Collector (devcode 2477).

Voltronic-family inverter on the DessMonitor platform. Evidence for the rating
and setting titles below is the diagnostics download in
``docs/evidence/devcodes/analysis_2477.json`` (#61).

``queryDeviceLastData`` returns the inverter's nameplate ratings and its own
setpoints alongside the live readings, as devcode 2452 does. The ratings are
facts about the hardware and become diagnostic sensors; the setpoints are
settings the account publishes as number and select entities, so they are
declared in ``SETTING_READINGS`` rather than mapped onto a sensor each. Of the
sixty-three titles this collector sent, twenty-two reached an entity and the
report told the owner that nineteen readings were missing when none were.

The titles, the setting list and the control option filtering live in
``eybond_voltronic``, which devcode 2341 shares: the two collectors send the
same titles and the same control field ids (#72, #73). What stays here is what
is this devcode's own - the hardware it names, and the operating modes its
collector has been seen to report.
"""

from __future__ import annotations

from .eybond_voltronic import (
    CHARGER_PRIORITY_MAPPING,
    OUTPUT_PRIORITY_MAPPING,
    SENSOR_TITLE_MAPPINGS,
    SETTING_READINGS,
    filter_control_options,
)

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2477)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": ["Novopal NP35PEU24"],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OPERATING_MODE_MAPPING: dict[str, str] = {"Line Mode": "Line"}

VALUE_TRANSFORMATIONS: dict = {}
PARAMETER_SENSOR_NAMES: set[str] = set()

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "control_options_filter": filter_control_options,
    "setting_readings": SETTING_READINGS,
}
