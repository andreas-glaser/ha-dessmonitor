"""Eybond Data Collector (devcode 6513).

ZAMDON all-in-one off-grid inverter with a lithium BMS link, reported through
the DessMonitor platform. Every mapping below comes from the redacted
diagnostics download in ``docs/evidence/devcodes/analysis_6513.json`` (#82),
which resolved 10 of 34 titles and dropped 18 that carry a unit.

The collector describes itself as a "Reverse control integrated machine": one
box holding the inverter and the charge controller, which report separately.
``Battery voltage`` is the inverter's measurement of the pack, ``MPPT battery
voltage`` the controller's, and ``BMS lithium battery voltage`` the pack's own,
and in the download they read 50.4, 50.2 and 49.94 V. Each keeps its own
sensor rather than being folded onto one.

Its spelling is its own: ``PV1 voltagee``, ``PV2 voltagee``, ``PV1 carging
current``, ``PV2 carging current``. The titles are mapped as sent; nothing is
corrected upstream of the mapping.

``Total solar power generation`` is the array's lifetime yield, 666 kWh here.
It maps onto PV Cumulative Energy, as devcode 697's does, and deliberately not
onto Energy Total: the summary endpoint already feeds that entity on this
account, and moving a reading onto an entity an installation already publishes
changes its identity and its history.

Left unmapped on purpose:

- ``Mains voltage``, ``PV1 low voltage``, ``PV2 low voltage`` and the alarm
  copy of ``Input frequency`` are alarm words, not measurements: each reads
  its own title back when the condition is present and ``--`` when it is not.
  The collector sends ``Input frequency`` twice, once as that word and once as
  the measured frequency, and the sensor takes the copy that carries a value.
- ``BMS lithium battery alarm information`` (0) is a raw word with no unit.
  Decoding it needs this BMS's alarm table, which no report carries.
- ``Adaptive protocol identification`` names the machine class rather than
  measuring anything.
- ``id`` and ``Timestamp`` are the payload's own identity fields.

``Maximum charging current of the controller`` reads 100 A against a
``Charging Current Setting`` control of 90 A and a ``Current Limit Setting`` of
500, so it is the controller's own limit rather than the readback of either,
and it becomes a diagnostic sensor rather than a declared setting. The twenty-
two control fields the account advertises need no mappings, and none of them is
repeated among the readings, so this profile declares no ``SETTING_READINGS``.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 6513)",
    "description": (
        "Data collector/gateway for ZAMDON all-in-one off-grid inverters "
        "with a lithium BMS link, reported through DessMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["ZAMDON all-in-one off-grid"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

# This collector reports no priority readings; both priorities reach Home
# Assistant as select entities labelled from the control template's own
# option lists.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

# "Inverted state" is the only state the download observed: the mains was
# absent, with the input at 4.0 V and 0.0 Hz. Any other string this collector
# uses is published as it spells it rather than taking the sensor down, so the
# list grows from evidence.
OPERATING_MODE_MAPPING: dict[str, str] = {
    "Inverted state": "Battery",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Mains side. Both read their absent values in the download.
    "Input voltage": "Grid Voltage",
    "Input frequency": "Grid Frequency",
    "Working state": "Operating mode",
    # The only temperature this collector reports, and it names no stage.
    "Temperature": "INV Module Termperature",
    # Charge controller.
    "MPPT battery voltage": "MPPT Battery Voltage",
    "MPPT discharge current": "MPPT Discharge Current",
    "Maximum charging current of the controller": "Controller Max Charging Current",
    "PV1 voltagee": "PV1 Voltage",
    "PV2 voltagee": "PV2 Voltage",
    "PV1 carging current": "PV1 Charger Current",
    "PV2 carging current": "PV2 Charger Current",
    "Total solar power generation": "PV Cumulative Power Generation",
    # The pack's own BMS, beside the inverter's measurements of it.
    "BMS lithium battery capacity SOC": "State of Charge",
    "BMS lithium battery voltage": "BMS battery voltage",
    "BMS lithium battery current": "BMS battery current",
    "Remaining capacity of BMS lithium battery": "BMS Remaining Capacity",
    "BMS Lithium battery rated capacity": "BMS Rated Capacity",
    "BMS lithium battery SOH": "BMS State of Health",
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
# The committed template is 22 owner settings: the battery voltage and
# SOC limits, the charging gears and currents, and the work pattern.
#
# The fields below are registered disabled instead. Each is destructive,
# irreversible or a grid-compliance setting, and none is something to change
# by accident; an owner who wants one enables it once.
CONTROLS_REVIEWED = True

PROTECTED_CONTROLS: frozenset[str] = frozenset(
    {
        # Remote switch setting, which stops the inverter
        "energy_use_modelph",
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
