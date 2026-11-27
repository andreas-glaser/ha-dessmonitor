"""Eybond Data Collector (devcode 752).

A Kstar KSG 5K DM single-phase on-grid string inverter with three trackers,
reported through ShineMonitor behind an IO-71653D-series collector. Evidence
is the integration diagnostics download in
``docs/evidence/devcodes/analysis_752.json`` (#95).

Five of its thirty-two titles resolved without a profile and twenty-two of
the rest carry a unit, which is what held the Repairs card open: all three
trackers, the array total, the R-phase grid measurements, both temperatures,
the DC bus and the lifetime energy counter.

**Why the energy sensors read zero.** ``Total energy`` stood at 33057 kWh in
the download while the plant summary's ``energyTotal`` read ``0.0000``, and
the summary is what fed the sensor. The inverter's own counter is mapped onto
``Energy Total``, and the summary's ``energyTotal`` and ``outpower`` are
mapped onto the readings they duplicate so the zero stops publishing an
entity beside the real one (#58, #75). ``energyToday`` has no counterpart:
this collector reports no daily energy figure at all, so that one keeps
reading the vendor's unset zero.

The bus is a single rail. ``PBUS voltage`` reads 375.2 V, which is a whole DC
link on a 230 V single-phase inverter rather than half of a split one -
devcode 2548's split bus reports 409 V on each side - so ``NBUS voltage`` is
declared absent rather than mapped.

Left unmapped on purpose:

- ``Grid connected number`` (``031841``) carries no unit and no report says
  what it counts. Its leading zero makes it a vendor string rather than a
  figure, and a sensor with a guessed meaning is worse than none.
- ``id``, ``Timestamp`` and ``Serial number`` are the record's own identity.
  The serial arrives blank, which is the redaction working.

The five control fields the account advertises are installer and remote-power
settings - remote shutdown and its cancel, the input mode, the power factor
and the clock - so this profile declares no ``CONTROLS_REVIEWED`` and all
five stay registered disabled. ``system_time`` is a clock, so it is declared
in ``TEMPORAL_CONTROLS`` and reaches the text platform rather than a number
entity that could not hold it. Nothing here is the readback of one of those
five, so there are no ``SETTING_READINGS``.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 752)",
    "description": (
        "Data collector/gateway for single-phase on-grid string inverters "
        "with up to three trackers, reported through ShineMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["Kstar KSG 5K DM single-phase on-grid, 3 MPPT"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "solar_tracking",
    ],
}

# A grid-tie inverter has no battery, so it reports no priorities or modes.
# Its state is "Operation mode", which reaches the Inverter Status text
# sensor below.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # The lifetime counter the owner saw as 0.0000, and the two summary
    # titles mapped onto the readings they duplicate. "Output power" already
    # resolves to Output Active Power on its own.
    "Total energy": "Energy Total",
    "energyTotal": "Energy Total",
    "outpower": "Output Active Power",
    # AC side. The S and T phases are declared absent below; this unit uses
    # the R phase, and its terminals are the grid connection.
    "R phase grid voltage": "Grid Voltage",
    "R phase grid current": "grid current",
    # The day's highest output power, 2232 W against 486 W live.
    "Today power peak": "Today Peak Power",
    # Trackers. The third reads 0.0 V, 0.00 A and 0 W on this unit, which is
    # an unused input rather than a field the collector never fills: the
    # other two carry 261.6 V / 1.14 A / 298 W and 208.1 V / 0.98 A / 204 W,
    # so the three behave as one set and are mapped as one.
    "PV1 input voltage": "PV1 Voltage",
    "PV2 input voltage": "PV2 Voltage",
    "PV3 input voltage": "PV3 Voltage",
    "PV1 input current": "PV1 Current",
    "PV2 input current": "PV2 Current",
    "PV3 input current": "PV3 Current",
    "PV1 input power": "MPPT1 Power",
    "PV2 input power": "MPPT2 Power",
    "PV3 input power": "MPPT3 Power",
    # 502 W against 298 + 204 from the two live trackers, so this is the
    # array total in watts and not the kilowatt summary figure.
    "PV total input power": "PV Power",
    # DC bus, a single rail on this hardware.
    "PBUS voltage": "Positive Bus Voltage",
    # Temperatures. The heatsink carries the figure; the module reading is
    # declared absent below.
    "Radiator temperature": "Inverter Radiator Temperature",
    # The inverter's own state, which this collector answers "NORMAL". A
    # word, and Inverter Status is already a text sensor, so it is not
    # offered to float() (#81).
    "Operation mode": "Inverter Status",
}

CONTROL_FIELD_MAPPINGS: dict[str, str] = {}

# The clock this collector publishes. On the number platform its value would
# be discarded on arrival, so the control appears with nothing in it and
# nothing to set.
TEMPORAL_CONTROLS: dict[str, str] = {
    "system_time": "text",
}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

SETTING_READINGS: set[str] = set()

# Fields this collector reports that the hardware behind it never fills. Each
# carries a unit, so without this declaration they count as readings that
# reach no entity and the owner is told readings are missing when none are
# (#58). Mapping them instead would publish sensors that read zero forever.
_IDLE_PHASE = (
    "the owner reports a single-phase unit and the download agrees: the R "
    "phase carries 237.0 V and 2.00 A while all four of these read 0 (#95)"
)
_SINGLE_RAIL_BUS = (
    "PBUS voltage reads 375.2 V, a whole DC link on a 230 V single-phase "
    "inverter rather than half of a split one, so there is no negative rail "
    "to measure; devcode 2548's split bus reports 409 V on each side (#95)"
)
_UNFITTED_SENSOR = (
    "the heatsink reads 34.8 °C on an inverter exporting 486 W, so a module "
    "at 0.0 °C beside it is an unfitted sensor rather than a measurement "
    "(#95)"
)

ABSENT_READINGS: dict[str, str] = {
    "S phase grid voltage": _IDLE_PHASE,
    "T phase grid voltage": _IDLE_PHASE,
    "S phase grid current": _IDLE_PHASE,
    "T phase grid current": _IDLE_PHASE,
    "NBUS voltage": _SINGLE_RAIL_BUS,
    "Module temperature": _UNFITTED_SENSOR,
}

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
    "absent_readings": ABSENT_READINGS,
}
