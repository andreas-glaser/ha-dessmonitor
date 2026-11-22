"""Eybond Data Collector (devcode 659).

A Windon LT21HD three-phase on-grid string inverter with two trackers,
reported through ShineMonitor behind a Wi-Fi Plug Pro-13 on firmware 3.1.0.1.
Evidence is the diagnostics download in
``docs/evidence/devcodes/analysis_659.json`` (#92).

Four of its forty-three readings resolved without a profile, and the
thirty-nine that did not include every figure the owner watches: all three
phases, both trackers, the day and lifetime energy counters and both
heatsinks. Twenty-eight of them carry a unit, which is what held the Repairs
card open.

**The same defect devcode 567 was reported for**: the plant summary leaves
``outpower``, ``energyToday`` and ``energyTotal`` at 0.0000 on this devcode
while the inverter reports 984 W and 79241.471 kWh itself, so Output Power
and both energy sensors read zero on a working inverter. All three summary
titles are mapped onto the device's own readings, which stops the merge
publishing a second entity for one measurement (#58, #75).

Unlike devcode 567 this unit measures each phase separately - a voltage, a
current, a frequency, an active power and an apparent power per phase - and
reports a phase voltage rather than a line-to-line one: 234.1 V, which is
400 V across the phases divided by the square root of three. So its three
voltages reach the Grid L1/L2/L3 Voltage sensors, where 567's reach the
line-to-line keys.

The platform answers ``queryDeviceCtrlField`` with ERR_FORBIDDEN for this
account, so the download records no control template at all. Nothing here is
a setting, and no control needs ``TEMPORAL_CONTROLS``.

Left unmapped on purpose:

- ``Debugging Information 1`` to ``6`` are raw vendor words, five of them 0
  and one 637 in the download, and no report carries the table that decodes
  them. Devcode 684's seven ``fault information`` words are left alone for
  the same reason.
- ``MCU1(DSP)``, ``MCU2(ARM1)`` and ``MCU3(ARM2) software version`` are
  firmware identity rather than telemetry. None carries a unit, and the
  single ``Software version`` key cannot hold three of them, so choosing one
  would be arbitrary.
- ``id``, ``Timestamp`` and ``SN`` are the record's own identity. ``SN``
  arrives blank, which is the redaction working.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 659)",
    "description": (
        "Data collector/gateway for three-phase on-grid string inverters "
        "that measure each phase separately, reported through ShineMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["Windon LT21HD three-phase on-grid, 2 MPPT"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "solar_tracking",
    ],
}

# A grid-tie inverter has no battery, so it reports no priorities. Its state
# is "mode inquiry", which reaches the Inverter Status text sensor below.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # The AC total, and the three summary titles the vendor leaves at
    # 0.0000, mapped onto the readings they duplicate.
    "AC total Active Power": "Output Active Power",
    "outpower": "Output Active Power",
    "Day Electricity": "Energy Today",
    "Total Power Generation": "Energy Total",
    "energyToday": "Energy Today",
    "energyTotal": "Energy Total",
    # Per-phase AC. "AC Side A Phase Voltage" reads 234.1 V, a phase voltage
    # and not a line-to-line one, so these are the Grid L1/L2/L3 keys rather
    # than the L1-L2 pair devcode 567 reports.
    "AC Side A Phase Voltage": "Grid L1 Voltage",
    "AC Side B Phase Voltage": "Grid L2 Voltage",
    "AC Side C Phase Voltage": "Grid L3 Voltage",
    "AC Side A Phase Current": "Grid L1 Current",
    "AC Side B Phase Current": "Grid L2 Current",
    "AC Side C Phase Current": "Grid L3 Current",
    "AC Side A Phase Frequency": "Grid L1 Frequency",
    "AC Side B Phase Frequency": "Grid L2 Frequency",
    "AC Side C Phase Frequency": "Grid L3 Frequency",
    "AC Side A Active Power": "Grid L1 Active Power",
    "AC Side B Active Power": "Grid L2 Active Power",
    "AC Side C Active Power": "Grid L3 Active Power",
    # Labelled "W" by the collector and published in volt-amperes: 366
    # against 333 W of active power on the same phase. See the keys' own note
    # in const.py.
    "AC Phase A Apparent Power": "Grid L1 Apparent Power",
    "AC Phase B Apparent Power": "Grid L2 Apparent Power",
    "AC Phase C Apparent Power": "Grid L3 Apparent Power",
    # DC side, two trackers. The power per tracker reaches the MPPT keys
    # added for devcode 567's four, and the voltage and current reach the PV
    # keys that already existed.
    "DC Input 1 Power": "MPPT1 Power",
    "DC Input 2 Power": "MPPT2 Power",
    "DC Input 1 Voltage": "PV1 Voltage",
    "DC Input 2 Voltage": "PV2 Voltage",
    "DC Input 1 current": "PV1 Current",
    "DC Input 2 current": "PV2 Current",
    # The inverter's own state, which this collector calls "mode inquiry"
    # and answers "Grid". A word, and Inverter Status is already a text
    # sensor, so it is not offered to float() (#81).
    "mode inquiry": "Inverter Status",
}

# "PV1 Insulation Resistance", "PV2 Insulation Resistance", "Radiator 1
# Temperature" and "Radiator 2 Temperature" need no entry: the canonical keys
# are named after the titles this collector already sends, so they resolve
# without a mapping. No other committed download sends any of those four.

CONTROL_FIELD_MAPPINGS: dict[str, str] = {}

TEMPORAL_CONTROLS: dict[str, str] = {}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

# The platform refuses this account's control template, so no reading here
# can be the readback of a control the same device advertises.
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
