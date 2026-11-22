"""Eybond Data Collector (devcode 2500).

A MUST PH18-family hybrid inverter on the DessMonitor platform. Evidence is
the diagnostics download in ``docs/evidence/devcodes/analysis_2500.json``,
taken on a MUST PH18 5.5KW behind a WI-FI PLUG14 RTU on firmware 3.4.1.1,
grid-tied with a battery at 53.4 V (#91).

Twenty-three of the twenty-five readings already resolved without a profile,
so this one is short. The collector speaks the same vocabulary as devcode
697 - ``PLoad``, ``PGrid``, ``PInverter``, ``Batt Current``, ``work state``
and the ``Accumulated ...`` counters - and ``SENSOR_TYPES`` already names all
of those. Two reached no entity and are what this profile adds. Both carry a
unit, which is why the Repairs card counted them.

Left as it is on purpose:

- ``work state`` reads ``Grid-Tie`` and reaches the Operating Mode sensor
  through its own canonical key. Mapping the title onto ``Operating mode``
  would normalise the label and also change the unique id of an entity every
  installation already running this devcode publishes, so it is not done
  here, for the same reason devcode 697 does not do it.
- ``outpower`` and ``energyToday`` come from the plant-summary endpoint and
  read 0.0000 on this account while the inverter reports 31 W through the
  inverter and 2556.30 kWh accumulated from the array. ``energyTotal`` is
  the exception and carries 2556.3000, the same figure as
  ``Accumulated PV Power``. Whether a summary field the vendor leaves
  unfilled should publish an entity at all is #75, and is not decided per
  devcode.
- ``id`` and ``Timestamp`` are the record's own identity, which the
  integration already treats as attributes rather than readings.

The account advertises twenty-one control fields and the telemetry repeats
none of them as a reading, so this profile declares no settings. None of them
holds a clock, so none needs ``TEMPORAL_CONTROLS``.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2500)",
    "description": (
        "Data collector/gateway for MUST PH18-family hybrid inverters, "
        "reported through DessMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["MUST PH18 5.5KW"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

# No reading in the download carries an output or charger priority: the
# charger source priority is a control field only, and its own label reaches
# the select entity unchanged.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

# "Grid-Tie" is the only value the download observed. A mapping here would
# widen the enum for every devcode without changing what this one publishes,
# because the value mapping is applied to the "Operating mode" title and this
# collector sends "work state".
OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Lifetime yield from the array, 2556.30 kWh in the download. Devcode 697
    # reports the same title and maps it to the same key.
    "Accumulated PV Power": "PV Cumulative Power Generation",
    # The exported lifetime counter attributed to the array. It reads 58 kWh
    # against "Accumulated Sell Power" also at 58, which this profile does
    # not take as proof that the two are one register: a system exporting
    # only solar agrees on both either way. See the key's own note in
    # const.py for why it is a sensor of its own rather than a mapping onto
    # the counter beside it.
    "accumulated PV_sell power": "Accumulated PV Sell Power",
}

CONTROL_FIELD_MAPPINGS: dict[str, str] = {}

TEMPORAL_CONTROLS: dict[str, str] = {}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

SETTING_READINGS: set[str] = set()

# This devcode's control template has been read against the committed
# evidence, so its controls are registered enabled rather than left for the
# owner to find (#90).
#
# The committed template is 21 owner settings: battery voltages, the
# charging currents, the charger priority and the inverter output.
#
# The fields below are registered disabled instead. Each is destructive,
# irreversible or a grid-compliance setting, and none is something to change
# by accident; an owner who wants one enables it once.
CONTROLS_REVIEWED = True

PROTECTED_CONTROLS: frozenset[str] = frozenset(
    {
        # Ongrid Switch, which disconnects the inverter
        "shutdown_work",
        # the grid compliance standard the unit was approved against
        "grid_protect_standard",
    }
)


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
    "controls_reviewed": CONTROLS_REVIEWED,
    "protected_controls": PROTECTED_CONTROLS,
}
