"""Eybond Data Collector (devcode 2341).

Voltronic-family inverter on the DessMonitor platform, sharing its titles and
its whole control template with devcode 2477: the same reading spellings, the
same vendor mistakes in them, and the same control field ids down to
``bat_sp_floting_charging_voltage``. The shared vocabulary is in
``eybond_voltronic``; evidence is the diagnostics download in
``docs/evidence/devcodes/analysis_2341.json``.

Reported twice on the same day, by an EASUN owner on firmware 3.2.1.1 and a
PowMr owner on 3.1.1.0 (#72, #73). All three devices sent an identical set of
45 titles that reached no entity, 41 of which this family already names. The
four that remain - Machine Type, Main CPU Version, Secondary CPU Version and
Battery Piece - identify the hardware, carry no unit on either devcode, and are
left unmapped rather than pushed onto a neighbouring sensor.

Both reporters' mains was out when they took their downloads, so "Invert Mode"
is the only operating mode any of the three has been observed in. A mode that
is not registered here is published as the collector spells it rather than
taking the sensor down, so the list grows from evidence instead of guesswork.
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
    "name": "Eybond Data Collector (devcode 2341)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": ["EASUN hybrid", "PowMr MPS-V plus 3.5 kW"],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

# "Invert Mode" is what this collector calls running off the battery, which is
# the spelling devcode 6416 reports and maps the same way.
OPERATING_MODE_MAPPING: dict[str, str] = {"Invert Mode": "Battery"}

VALUE_TRANSFORMATIONS: dict = {}

# Its parameters endpoint answers with Battery Voltage, Battery Charging
# Current, AC Input Frequency and PV Input Power, all of which the telemetry
# call already carries, so there is nothing to fetch separately.
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
