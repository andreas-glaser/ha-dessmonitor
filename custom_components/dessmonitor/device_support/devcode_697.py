"""Eybond Data Collector (devcode 697).

A PV1800-family off-grid inverter reported on the ShineMonitor platform.
Evidence is the diagnostics download in
``docs/evidence/devcodes/analysis_697.json``, taken on an MD PV18-5048 VHM
(5000 W / 48 V, sold as CYMPOWER) with two Pylontech US3000C batteries and no
grid connection (#79).

Eighteen of the twenty-one readings already resolved without a profile, which
is why this one is short: the collector uses the ShineMonitor spellings that
``SENSOR_TYPES`` already names, ``PLoad``, ``PGrid``, ``PInverter``,
``Batt Current`` and the ``Accumulated ...`` counters among them. Three
reached no entity and are what this profile adds.

``Charger Current`` and ``Charger Power`` are measured on the battery side,
not the array: the download has 49.0 V battery voltage against 2.2 A and
108 W, and 49.0 x 2.2 = 107.8. The collector does not say which source is
charging, and this inverter can charge from either, so the two keep the
vendor's own names rather than being mapped onto the PV or AC charging keys -
the reporter's unit was off-grid when the download was taken, which says
nothing about the field.

Left as it is on purpose:

- ``work state`` reads ``OffGrid`` and reaches the Operating Mode sensor
  through its own canonical key. Mapping the title onto ``Operating mode``, as
  devcode 6422 does, would normalise the label but also change the entity's
  unique id on every installation already running this devcode, so it is not
  done here.
- ``outpower``, ``energyToday`` and ``energyTotal`` come from the plant-summary
  endpoint and all three read 0.0000 on this account while the inverter
  reports 217 W through the inverter and 3920 kWh accumulated from the array.
  That is the defect tracked in #75, which is about whether a summary field the
  vendor leaves unfilled should publish an entity at all, and it is not decided
  per devcode.
- ``id`` and ``Timestamp`` are the record's own identity, and the integration
  already treats them as attributes rather than readings.

The account advertises twenty-four control fields, none of which the telemetry
repeats as a reading, so this profile declares no settings. The charger-source
priority control carries the vendor's ``Soalr first`` misspelling in its option
list; it is the platform's own label and no reading resolves against it.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 697)",
    "description": (
        "Data collector/gateway for PV1800-family off-grid inverters, "
        "reported through ShineMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["PV1800 MD PV18-5048 VHM 5 kW 48 V (CYMPOWER)"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

# No reading in the download carries an output or charger priority, so there is
# nothing for a value mapping to act on. The control template's own enums reach
# the select entities unchanged.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

# "OffGrid" is the only value the download observed, and the operating-mode
# enum already offers it. A mapping here would widen the enum for every
# devcode without changing what this one publishes, because the value mapping
# is applied to the "Operating mode" title and this collector sends
# "work state".
OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Lifetime yield from the array, 3920 kWh in the download. It is the
    # counter the owner wants on the energy dashboard, and it is not the
    # summary endpoint's energyTotal, which this account leaves at 0.0000.
    "Accumulated PV Power": "PV Cumulative Power Generation",
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
