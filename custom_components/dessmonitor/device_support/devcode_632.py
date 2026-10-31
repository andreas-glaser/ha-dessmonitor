"""ShineMonitor Data Collector (devcode 632).

Mappings come from the redacted analysis in
``docs/evidence/devcodes/analysis_632.json`` (#58). Like devcode 4743 this is a
grid-connected PV inverter with no battery: its controls are grid over- and
under-voltage and frequency protection points plus an external meter, and its
telemetry carries no battery, charger or priority readings.

``Energy today`` already resolved on its own, which is why the reporter saw a
working daily figure and a total stuck at 0 kWh: the vendor spells the total
``energy_total``, which resolved to nothing and was dropped in silence.

The inverter reports R, S and T phases and the RS, ST and TR line voltages
whatever its phase count, and the readings this unit returns are single-phase
in magnitude. The R phase is mapped to the grid sensors; S, T and the line
voltages stay unmapped until a confirmed three-phase report shows them
carrying a load. ``DCI``, ``GFCI`` and ``ISO`` are left unmapped as well: they
are leakage-current and insulation-resistance readings whose unit the analysis
does not record, and a sensor with a guessed unit is worse than none.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "ShineMonitor Data Collector (devcode 632)",
    "description": (
        "Data collector/gateway for grid-connected PV inverters with up to "
        "three strings and an optional export meter, reported through "
        "ShineMonitor"
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
    # AC side.
    "Grid R voltage": "Grid Voltage",
    "Grid R current": "grid current",
    "Output S": "Output Apparent Power",
    "Output Q": "Output Reactive Power",
    "Output PF": "Power Factor",
    "Instrument power": "Meter Power",
    # Strings.
    "PV1 voltage": "PV1 Voltage",
    "PV2 voltage": "PV2 Voltage",
    "PV3 voltage": "PV3 Voltage",
    "PV1 current": "PV1 Current",
    "PV2 current": "PV2 Current",
    "PV3 current": "PV3 Current",
    # DC bus.
    "bus voltage": "Bus Voltage",
    # The total the reporter saw as 0 kWh while the daily figure worked (#58).
    "energy_total": "Energy Total",
    # Status and counters.
    "Inverter status": "Inverter Status",
    "Waiting time": "Grid Reconnect Waiting Time",
    "cumulative time": "Operating Time",
    # Temperatures.
    "Internal radiator temperature": "Inverter Radiator Temperature",
    "Internal ambient temperature": "Ambient Temperature",
}

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
}
