"""Eybond Data Collector (devcode 684).

Mappings come from the redacted diagnostics download in
``docs/evidence/devcodes/analysis_684.json`` (#62), taken on a Panther Solar
PES-3000TL-SS reported through the SmartClient for Solar app, i.e. the
ShineMonitor platform. The reporter's nameplate photograph agrees with what
the collector reports about itself: 3000 W nominal AC against ``rate power``
3000 W, 230 V nominal grid voltage against ``rate voltage`` 230.0 V, and a
single MPP tracker (100 to 450 V, 14 A) against ``MPPT channel`` 1 and
``device type`` "single channel single phase inverter". The reporter also
confirmed Energy Total, PV1 Voltage and Grid Voltage against the app.

``DC voltage 2`` and ``DC current 2`` stay mapped even though they read 0 on
that unit, which has one tracker: this profile serves the devcode rather than
one inverter, and a two-string unit reporting the same titles would lose real
readings.

Like devcodes 518, 632 and 4743 this is a grid-connected PV inverter with no
battery: its telemetry carries no battery, charger or priority readings, and
the account answered ``queryDeviceCtrlField`` with ``ERR_NO_RECORD``, so it
advertises no controls at all.

The titles are the lower-cased, spelled-out Eybond set devcode 518 also
reports (``today energy``, ``total energy``, ``DC voltage 1``), which is why 31
of the 39 readings in the download resolved to nothing. The two DC strings are
mapped to the plain ``PV1``/``PV2`` keys rather than the charger-current ones:
a grid-tie inverter has nothing to charge.

Left unmapped on purpose:

- ``fault information 1`` to ``7`` carry no unit and are raw bitmask words. A
  sensor per word would publish seven numbers nobody can read; decoding them
  needs the vendor's fault table for this protocol, which no report has yet.
- ``safety regulation``, ``MPPT channel``, ``register number``, ``device
  type``, ``device address`` and the three protocol versions are identity and
  configuration fields, not readings.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 684)",
    "description": (
        "Data collector/gateway for single-phase grid-connected PV inverters "
        "with two strings, reported through ShineMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["Panther Solar PES-3000TL-SS"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "solar_tracking",
    ],
}

# A grid-tie inverter has no battery, so it reports no priorities.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

# "normal" is the only value the download observed. It is exposed as-is rather
# than read as one of the canonical modes: nothing here shows what this
# collector calls standby, a fault or an export limit.
OPERATING_MODE_MAPPING: dict[str, str] = {
    "normal": "Normal",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # AC side. The inverter labels its single phase "A".
    "grid voltage A": "Grid Voltage",
    "grid current A": "Grid Current",
    # Strings.
    "DC voltage 1": "PV1 Voltage",
    "DC voltage 2": "PV2 Voltage",
    "DC current 1": "PV1 Current",
    "DC current 2": "PV2 Current",
    # Energy counters.
    "today energy": "Energy Today",
    "total energy": "Energy Total",
    # Temperatures.
    "radiator temperature": "Inverter Radiator Temperature",
    "inductor temperature": "Inductor Temperature",
    "inside temperature": "Inside Temperature",
    # Nameplate ratings.
    "rate power": "Rated Power",
    "rate voltage": "Rated Voltage",
    # Status.
    "work mode": "Operating mode",
}

CONTROL_FIELD_MAPPINGS: dict[str, str] = {}

TEMPORAL_CONTROLS: dict[str, str] = {}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

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
}
