"""Eybond Data Collector (devcode 4743).

Mappings come from the redacted analysis in
``docs/evidence/devcodes/analysis_4743.json`` (#58). The collector reports a
single-phase grid-connected PV inverter: ``InverterType`` reads
``Single-phase Grid-Connected Inverter`` and its controls are grid-protection
settings, not battery or charger settings. There is no battery anywhere in its
telemetry, so none of the battery or priority mappings apply.

The inverter reports R, S and T phase readings regardless of how many phases it
has, and this unit uses the R phase. Its AC terminals are on the grid, so the
R-phase voltage, current, frequency and power are mapped to the grid sensors,
which is also the AC grid voltage the reporter asked for. The S and T phases
are declared in ``ABSENT_READINGS``: on a single-phase unit they are idle, and
mapping them before a confirmed three-phase report would publish sensors that
read zero forever. Declaring them is what keeps them out of the missing-reading
count, which told the reporter sixteen readings were missing when none were.

The analysis records a unit for its first twenty readings only, which is all
the CLI captures, so the ``power H`` titles were mapped as watts because every
power reading it does carry is in watts. The reporter's own figures confirmed
that scale: 265 V and 1.6 A on string 1 against 424 W of grid power.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 4743)",
    "description": (
        "Data collector/gateway for single-phase grid-connected PV inverters "
        "with up to three strings, reported through ShineMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": [],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "solar_tracking",
        "parameter_control",
    ],
}

# A grid-tie inverter has no battery, so it reports no priorities or modes.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # AC side. The inverter's own terminals are the grid connection.
    "Inverter R-phase voltage": "Grid Voltage",
    "Inverter R-phase current": "grid current",
    "Inverter R-phase frequency": "Grid Frequency",
    "Inverter R-phase power H": "Grid Power",
    "Inverter three-phase power H": "Output Active Power",
    "Inverter three-phase reactive power H": "Output Reactive Power",
    "Inverter power factor": "Power Factor",
    # Load side, which this collector reports separately from the inverter side.
    "Load R-phase voltage": "Output Voltage",
    "Three-phase total load power H": "PLoad",
    # On a single-phase unit the R phase carries the whole load, so this is the
    # same measurement as the three-phase total above. Both titles reach one
    # entity, which takes whichever the collector reports.
    "R-phase load power H": "PLoad",
    # Strings. "Total PV power" is in watts here, and without this mapping it
    # resolves by friendly name onto the kilowatt "outpower" sensor and reads a
    # thousand times high.
    "Total PV power": "PV Power",
    "PV1 voltage": "PV1 Voltage",
    "PV2 voltage": "PV2 Voltage",
    "PV3 voltage": "PV3 Voltage",
    "PV1 current": "PV1 Current",
    "PV2 current": "PV2 Current",
    "PV3 current": "PV3 Current",
    # "PV1 power", "PV2 power" and "PV3 power" are declared in
    # ABSENT_READINGS below: this collector leaves them at 0 while the string
    # produces, and "Total PV power" carries the real figure.
    # DC bus.
    "bus voltage": "Bus Voltage",
    "Positive bus voltage": "Positive Bus Voltage",
    "Negative bus voltage": "Negative Bus Voltage",
    # Energy counters, which reported 0 kWh while unmapped (#58).
    "PV power generation today": "Energy Today",
    "Total photovoltaic power generation": "Energy Total",
    # Temperatures.
    "InverterTemp": "INV Module Termperature",
    "DC Temp": "DC Module Termperature",
}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

# Fields this collector reports that the hardware behind it never fills. Each
# carries a unit, so without this declaration they count as readings that reach
# no entity, and the owner is told readings are missing when none are (#58).
# Mapping them instead would publish sensors that read zero forever.
_IDLE_PHASE = (
    "this unit reports InverterType 'Single-phase Grid-Connected Inverter' and "
    "uses the R phase, so the S and T phases carry nothing (#58)"
)
_UNFILLED_STRING_POWER = (
    "the collector reports 0 while the string produces: 220.5 V and 7.3 A on "
    "string 1 against a 1552 W total in the committed analysis, and 265 V and "
    "1.6 A against 424 W of export on live hardware (#58)"
)

ABSENT_READINGS: dict[str, str] = {
    "Inverter S-phase voltage": _IDLE_PHASE,
    "Inverter S-phase current": _IDLE_PHASE,
    "Inverter S-phase frequency": _IDLE_PHASE,
    "Inverter S-phase power H": _IDLE_PHASE,
    "Inverter T-phase voltage": _IDLE_PHASE,
    "Inverter T-phase current": _IDLE_PHASE,
    "Inverter T-phase frequency": _IDLE_PHASE,
    "Inverter T-phase power H": _IDLE_PHASE,
    "Load S-phase voltage": _IDLE_PHASE,
    "Load T-phase voltage": _IDLE_PHASE,
    "S-phase load power H": _IDLE_PHASE,
    "T-phase load power H": _IDLE_PHASE,
    "PV1 power": _UNFILLED_STRING_POWER,
    "PV2 power": _UNFILLED_STRING_POWER,
    "PV3 power": _UNFILLED_STRING_POWER,
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "absent_readings": ABSENT_READINGS,
}
