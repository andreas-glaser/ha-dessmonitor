"""Eybond Data Collector (devcode 2548).

Three-phase hybrid inverter on the DessMonitor platform, reported as an
SPI-12K-H3 of 12 kW whose own ``Equipment type`` reads ``ASF48120S260-H``
(#67). Evidence is the diagnostics download in
``docs/evidence/devcodes/analysis_2548.json``.

This is the first three-phase unit with a profile, and it names its phases two
ways at once: phase A carries titles such as "Inverter A phase voltage" and
"Load A phase current", while the other two are prefixed "L2:" and "L3:". Phase
A is L1, so the mappings below bring all three into one naming.

It also separates two currents a single-phase profile does not: the inverter's
own output current per phase ("Inverter A phase current", "L2:Inverting
current") and what the load draws ("Load A phase current", "L2:Load current").
They differ whenever the unit runs on bypass, so they are different sensors.

Two readings are mapped on inference rather than on a statement by the vendor,
and both are recorded in #67 so the next reader can see which:

- "charging power" is taken as the battery's charging power. It read 0 W in the
  download, which is consistent but does not prove it.
- "PV power generation on the day" is taken as the day's generation, following
  devcode 6515's "Daily PV energy generation". It read 3.7 kWh beside an
  ``energyToday`` of 3.7, so the two are the same quantity and resolve to one
  sensor rather than two.

The download carried no control template - the cloud had fallen back to a
cached snapshot for this device - so which of its mode titles are controls
could not be checked. None of them carries a unit, so none is counted as a
missing reading, and none is declared a setting on a guess.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2548)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": ["SPI-12K-H3 (ASF48120S260-H), 12 kW three-phase"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}
CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

# "contravariant" is the collector's own English for this state and is almost
# certainly a rendering of the Chinese for "inverting". It is deliberately not
# translated into one of the canonical modes: nothing in the download says
# which, and a mode that is not registered here is published as the collector
# spells it rather than taking the sensor down, so the reading reaches the
# owner either way and the mapping can follow once #67 confirms what the
# inverter's own screen shows.
OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "Battery SOC": "SOC",
    "The current state of the machine": "Operating mode",
    "Charging mode": "Charge Mode",
    "Temperature of transformer": "Transformer temperature",
    "Total active power of the load": "PLoad",
    "Total output voltage": "Total Output Voltage",
    # Battery charging. Inferred; see the module docstring.
    "charging power": "Battery Charging Power",
    "Mains charging current": "AC charging current",
    # Solar strings. The collector reports both panels and their total.
    "Solar panel 1 voltage": "PV1 Voltage",
    "Solar panel 1 current": "PV1 Current",
    "Solar panel 1 power": "PV1 Charger Power",
    "Solar panel 2 voltage": "PV2 Voltage",
    "Solar panel 2 current": "PV2 Current",
    "Solar panel 2 power": "PV2 Charger Power",
    "Solar total panel power": "PV Power",
    # The same quantity the summary endpoint returns as energyToday, so both
    # reach one sensor rather than publishing the figure twice.
    "PV power generation on the day": "Energy Today",
    # Mains per phase. This unit reports no single combined mains voltage.
    "L1:Mains voltage": "Grid L1 Voltage",
    "L2:Mains voltage": "Grid L2 Voltage",
    # The vendor's lower-case "mains" on the third phase only.
    "L3:mains voltage": "Grid L3 Voltage",
    # Inverter output per phase. Phase A is L1.
    "Inverter A phase voltage": "Output L1 Voltage",
    "L2:Output voltage": "Output L2 Voltage",
    "L3:Output voltage": "Output L3 Voltage",
    "Inverter A phase current": "Output L1 Current",
    "L2:Inverting current": "Output L2 Current",
    "L3:Inverting current": "Output L3 Current",
    # What the load draws per phase, which is not the same as the above.
    "Load A phase active power": "Output L1 Active Power",
    "L2:Load active power": "Output L2 Active Power",
    "L3:Load active power": "Output L3 Active Power",
    # "Load A is phased at power" is the vendor's English for the apparent
    # power of phase A; it is reported in VA beside the two "L_:Load apparent
    # power" titles.
    "Load A is phased at power": "Output L1 Apparent Power",
    "L2:Load apparent power": "Output L2 Apparent Power",
    "L3:Load apparent power": "Output L3 Apparent Power",
    "Load A phase current": "Load L1 Current",
    "L2:Load current": "Load L2 Current",
    "L3:Load current": "Load L3 Current",
    "A phase load rate": "Load L1 Percentage",
    "L2:Load rate": "Load L2 Percentage",
    "L3:Load rate": "Load L3 Percentage",
    # Energy and ampere-hour counters. The four battery energy counters arrive
    # in watt-hours and the registry scales them from that label.
    "battery energy today charge": "Battery Energy Today (Charge)",
    "battery energy today discharge": "Battery Energy Today (Discharge)",
    "battery energy total charge": "Battery Energy Total (Charge)",
    "battery energy total discharge": "Battery Energy Total (Discharge)",
    "Battery charging ampere hours in the same day": "Daily Battery Charge Ah",
    "Battery discharge ampere hours per day": "Daily Battery Discharge Ah",
    "The battery accumulates ampere-hours of charge": ("Accumulated Battery Charge Ah"),
    "The cumulative number of ampere hours of battery discharge": (
        "Accumulated Battery Discharge Ah"
    ),
    "The number of ampere hours of mains charging on the same day": (
        "Daily Mains Charge Ah"
    ),
    "Cumulative charging capacity of mains": "Accumulated Mains Charge Ah",
    "Load cumulative power consumption": "Accumulated Load Power",
    "The electricity consumption of the load on the day": "Daily Load Energy",
    "The load accumulates the power consumption of the mains power": (
        "Accumulated Mains Load Energy"
    ),
    "The load consumes electricity from the mains on the same day": (
        "Daily Mains Load Energy"
    ),
}

VALUE_TRANSFORMATIONS: dict = {}

# The collector returns the four battery energy counters in watt-hours while
# the sensors publish kilowatt-hours, and labels them "Wh" itself. These
# entries only state what the download showed, for a payload that sends the
# value without the unit.
SOURCE_UNITS: dict[str, str] = {
    "Battery Energy Today (Charge)": "Wh",
    "Battery Energy Today (Discharge)": "Wh",
    "Battery Energy Total (Charge)": "Wh",
    "Battery Energy Total (Discharge)": "Wh",
}

PARAMETER_SENSOR_NAMES: set[str] = set()

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "source_units": SOURCE_UNITS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
}
