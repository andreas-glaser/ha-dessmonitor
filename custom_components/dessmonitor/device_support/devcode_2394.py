"""Eybond Data Collector (devcode 2394).

A 24 V off-grid inverter/charger sold as an MPPT24V-60A-5000W, reported
through the DessMonitor platform. Evidence is the device diagnostics download
in ``docs/evidence/devcodes/analysis_2394.json`` (#94).

This collector reports ten readings and nothing else, which is the smallest
vocabulary any committed download carries: the mains input, the AC output, the
load, the battery and one temperature. Seven of them already resolved; the
three that did not all carry a unit, which is what held the Repairs card open.

The spelling is devcode 6513's, down to the bare ``temperature``, so the three
mappings are the ones that profile already makes: ``Input voltage`` and
``Input frequency`` are the mains side, and the single unqualified temperature
is the inverter's own module reading, because the collector names no stage.

The plant summary's ``outpower``, ``energyToday`` and ``energyTotal`` read
``0.0000`` on this account while the inverter runs at 6 percent load, and
nothing can be done about it here: unlike devcodes 567 and 659 this collector
reports no power or energy figure of its own for them to be mapped onto.

Left unmapped on purpose: ``id`` and ``Timestamp`` are the record's own
identity and carry no unit.

The three control fields the account advertises are the inverter's own power
switch - turn on, standby and turn off the AC output - so this profile
declares no ``CONTROLS_REVIEWED`` and all three stay registered disabled.
Nothing here is the readback of one of them, so there are no
``SETTING_READINGS`` either.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2394)",
    "description": (
        "Data collector/gateway for 24 V off-grid inverter/chargers, "
        "reported through DessMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["MPPT24V-60A-5000W 24 V off-grid"],
    "supported_features": [
        "real_time_monitoring",
        "battery_management",
        "parameter_control",
    ],
}

# This collector reports no priority or mode readings at all.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Mains side, reading 219.0 V and 50.0 Hz in the download.
    "Input voltage": "Grid Voltage",
    "Input frequency": "Grid Frequency",
    # The only temperature this collector reports, and it names no stage, so
    # it reaches the same key devcode 6513's single "Temperature" does.
    "temperature": "INV Module Termperature",
}

CONTROL_FIELD_MAPPINGS: dict[str, str] = {}

TEMPORAL_CONTROLS: dict[str, str] = {}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

SETTING_READINGS: set[str] = set()

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
