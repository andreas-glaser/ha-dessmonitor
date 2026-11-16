"""Solar grid-tie inverter (devcode 518).

Single-/three-phase string inverter reported on the ShineMonitor solar
platform (e.g. Q0025-series data loggers). Verified with a SmartClient for
Solar account; not verified on SmartESS. queryDeviceLastData returns lower-cased,
spelled-out field titles ("active power", "total energy", "today energy") that
do not match the integration's canonical sensor names, so without this mapping
the energy and power sensors stay at 0 even though the data is present.

Field titles captured from a live devcode 518 inverter (BRAZIL-H grid profile).
The download is committed as ``docs/evidence/devcodes/analysis_518.json``
(#83).

This collector labels every channel it reports: three phases on the AC side
and four DC inputs, whatever the hardware behind it has. Each one is therefore
mapped to its own phase- or string-numbered sensor rather than onto the plain
``Grid Voltage`` and ``grid current`` keys, as devcode 632 maps its R phase.
Two things make that the wrong shape here: devcode 518 covers single- and
three-phase inverters, and the single-phase unit in the committed evidence
reports its measurement on phase C, not on phase A. Mapping the measuring
phase onto the plain keys would mean assuming which phase a different
installation measures on, and declaring the idle ones absent would hide a
three-phase owner's real readings.

So on a single-phase, two-string unit four of these sensors read 0.0 and two
read the 0.1 A floor the dark strings on inputs 1 and 2 also show. They are
what the collector sends, and an owner can disable the ones their hardware
does not have.

``DC current 1`` and ``DC current 2`` keep the ``PV1``/``PV2 Charger Current``
names they were given: a grid-tie inverter has no charger, but those entities
are published on installations already and renaming one is a deliberate
change of its own. The third and fourth inputs use the plain ``PV3``/``PV4
Current`` names.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Solar Grid-Tie Inverter (devcode 518)",
    "description": "String PV grid-tie inverter",
    "manufacturer": "Eybond",
    "known_inverters": ["BYD BYD-S-1P5K-2M"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "solar_tracking",
    ],
}

# Raw API title -> canonical name present in const.SENSOR_TYPES.
SENSOR_TITLE_MAPPINGS = {
    "active power": "Output Active Power",
    "DC output power": "PV Power",
    "total energy": "Energy Total",
    "today energy": "Energy Today",
    # Dashboard summaries must resolve to the same entities as live readings.
    "energyToday": "Energy Today",
    "energyTotal": "Energy Total",
    "current year generating capacity": "Energy Year",
    "grid frequency": "Grid Frequency",
    "inverter temperature": "INV Module Termperature",
    "DC voltage 1": "PV1 Voltage",
    "DC current 1": "PV1 Charger Current",
    "DC voltage 2": "PV2 Voltage",
    "DC current 2": "PV2 Charger Current",
    "DC voltage 3": "PV3 Voltage",
    "DC current 3": "PV3 Current",
    "DC voltage 4": "PV4 Voltage",
    "DC current 4": "PV4 Current",
    "apparent power value": "Output Apparent Power",
    # AC side, per phase. The vendor sends the line voltage and the phase
    # voltage under one title; on the single-phase unit in the evidence the
    # value is the phase voltage.
    "AB voltage/A phase voltage": "Grid L1 Voltage",
    "BC voltage/B phase voltage": "Grid L2 Voltage",
    "CA voltage/C phase voltage": "Grid L3 Voltage",
    "A phase current": "Output L1 Current",
    "B phase current": "Output L2 Current",
    "C phase current": "Output L3 Current",
    # DC link.
    "DC bus voltage": "Bus Voltage",
    "DC bus half voltage": "Bus Half Voltage",
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
}
