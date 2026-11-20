"""Eybond Data Collector (devcode 567).

Mappings come from the diagnostics download in #89, taken on a 10 kW 400 V
three-phase on-grid inverter with four trackers and twenty strings, reported
through the SmartClient for Solar app, i.e. the ShineMonitor platform. The
collector agrees with the owner's description of the hardware: ``Rated power``
10 kW against ``Rated voltage`` 400 V, four MPPT voltages and four MPPT
powers, and twenty per-string input currents.

Two captures were taken, 36 minutes apart and both after sunset, so every
instantaneous figure reads zero in them. The titles and units are what a
profile is written from and the two captures agree on those; the one figure
read from them is the lifetime counter, which moved from 24095.64 to
24096.62 kWh and confirms the counter is in kilowatt-hours already.

**The reason the owner opened the issue** is that this devcode leaves the
plant summary's ``outpower``, ``energyToday`` and ``energyTotal`` at 0.0000
while reporting the real figures itself, so the Output Power and both energy
sensors read zero on a working inverter. All three summary titles are mapped
onto the device's own readings here, which is what stops the merge publishing
a second entity for one measurement and reading zero through it (#58, #75).

Like devcodes 518, 632, 684 and 4743 this is a grid-connected PV inverter with
no battery: its telemetry carries no battery, charger or priority readings, so
the priority and operating-mode tables are empty. Unlike them it advertises 96
control fields, which is a problem of its own and is tracked in #90.

Left unmapped on purpose:

- ``Inverter Boot Time`` and ``Inverter Shutdown Time`` are timestamps, and
  the four ``Software version_*``, two ``Parameter version_*`` and
  ``Communication protocol version`` strings are firmware identity rather than
  telemetry. None carries a unit, so none counts as a reading reaching no
  entity. The single ``Software version`` key cannot hold four of them and
  choosing one of the four would be arbitrary.
- ``Device e-SN`` is the inverter's serial number. It is redacted from the
  download rather than published.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 567)",
    "description": (
        "Data collector/gateway for three-phase on-grid string inverters "
        "with up to four trackers, reported through ShineMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["10 kW 400 V three-phase on-grid, 4 MPPT / 20 strings"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "solar_tracking",
        "parameter_control",
    ],
}

# A grid-tie inverter has no battery, so it reports no priorities, and nothing
# in either capture carries an operating-mode value: the state is reported as
# "Inverter status", which reaches its own text sensor.
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # AC side. The collector reports kW and kVar and the sensors publish W and
    # VA; the scale is applied generically from the unit the collector
    # declares, in device_registry.normalize_reading_scale.
    "AC Active Power": "Output Active Power",
    "AC Reactive Power": "Output Reactive Power",
    # The plant summary leaves all three of these at 0.0000 on this devcode
    # while the inverter reports the real figures, so each summary title is
    # mapped onto the reading it duplicates.
    "outpower": "Output Active Power",
    "energyToday": "Energy Today",
    "energyTotal": "Energy Total",
    "Daily power generation": "Energy Today",
    "Cumulative power generation": "Energy Total",
    # Three-phase AC. These are the line-to-line voltages, 404 V on a 400 V
    # system, and the per-phase currents.
    "Grid AB Line Voltage": "Grid L1-L2 Voltage",
    "Grid BC Line Voltage": "Grid L2-L3 Voltage",
    "Grid CA Line Voltage": "Grid L3-L1 Voltage",
    "Grid A Phase Current (Ia)": "Grid L1 Current",
    "Grid B Phase Current (Ib)": "Grid L2 Current",
    "Grid C Phase Current (Ic)": "Grid L3 Current",
    # DC side. "DC Input Power" is the array total; the four MPPT figures are
    # per tracker.
    "DC Input Power": "PV Power",
    "MPPT1 input voltage": "PV1 Voltage",
    "MPPT2 input voltage": "PV2 Voltage",
    "MPPT3 input voltage": "PV3 Voltage",
    "MPPT4 input voltage": "PV4 Voltage",
    "MPPT1 Input Power": "MPPT1 Power",
    "MPPT2 Input Power": "MPPT2 Power",
    "MPPT3 Input Power": "MPPT3 Power",
    "MPPT4 Input Power": "MPPT4 Power",
    # Diagnostics the inverter measures about itself.
    "Internal Temperature": "Inside Temperature",
    "Inverter Efficiency": "Inverter Efficiency",
    "Insulation Resistance": "Insulation Resistance",
    "Daily Running Time": "Daily Running Time",
    "Cumulative Running Time": "Operating Time",
    "CO2 Reduction": "CO2 Reduction",
    # Status words. "Inverter status" already resolves to Inverter Status; the
    # switch is a second, separate state the collector reports beside it.
    "Inverter Switch Status": "Inverter Switch Status",
    "PID status": "PID Status",
}

# Twenty strings across four trackers, one current each. The vendor's own
# numbering, zero-padded, so the mapping is the identity for every one of them
# and exists to tie the titles to canonical keys rather than to rename them.
SENSOR_TITLE_MAPPINGS.update(
    {
        f"String{number:02d} Input Current": f"String{number:02d} Current"
        for number in range(1, 21)
    }
)

# The two fields whose value is a clock. A number entity cannot hold
# "2026-11-19 16:51:48", so the value is discarded on arrival and the control
# appears with nothing in it and nothing to set (#48, #57, #53). Both read a
# full calendar string in the download, so both are text rather than time.
# "Current date and time" is also the one field the vendor labels with a unit
# of "A", which is its own mistake and not a current.
TEMPORAL_CONTROLS: dict[str, str] = {
    "current_date_and_time": "text",
    "system_time": "text",
}

CONTROL_FIELD_MAPPINGS: dict[str, str] = {}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

# The account answers queryDeviceParsEs with nothing, and no reading here is a
# setpoint the control template repeats.
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
