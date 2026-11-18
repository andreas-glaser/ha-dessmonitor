"""Eybond Data Collector (devcode 2449).

Axpert-family off-grid inverter on the DessMonitor platform. Evidence for the
rating and setting titles below is the diagnostics download in
``docs/evidence/devcodes/analysis_2449.json``, taken on a SILA MAX 7200MH
(#80).

``queryDeviceLastData`` returns the inverter's nameplate ratings and its own
setpoints alongside the live readings, the same shape devcode 2452 reports.
The ratings are facts about the hardware and become diagnostic sensors; the
setpoints are the values of controls the same account already publishes, so
they are declared in ``SETTING_READINGS`` rather than mapped onto a sensor
each. Without that the support report counted all fourteen as readings that
reach no entity and the Repairs card said readings were missing when none
were.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2449)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": [
        "EASUN 8KWA",
        "EASUN 11KWA",
        "SILA MAX 7200MH",
        "WKS Evo MAX II 10kVA 48V",
    ],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "Utility Solar Bat": "Utility → Solar → Battery",
    "Solar Utility Bat": "Solar → Utility → Battery",
    "Solar Bat Utility": "Solar → Battery → Utility",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "Solar First": "PV First",
    "Solar + Utility": "PV Is At The Same Level As Utility",
    "Only Solar Charging Permitted": "Only PV",
}

OPERATING_MODE_MAPPING: dict[str, str] = {
    "Mains operation": "Grid Mode",
    "Line Mode": "Grid Mode",
    "Battery operation": "Battery Mode",
    "Inverting operation": "Off-grid Mode",
    "Inverter Operation": "Off-grid Mode",
    "Inverter operation": "Off-grid Mode",
    "PV operation": "Solar Mode",
    "Standby": "Standby",
    "Inverter Fault": "Fault",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Output Active Power": "Output Active Power",
    "AC Output Apparent Power": "Output Apparent Power",
    "AC Output Frequency": "Output Frequency",
    "AC Output Voltage": "Output Voltage",
    "Battery Capacity": "State of Charge",
    "Output Load Percent": "Load Percent",
    "Output Source Priority": "Output priority",
    "PV1 Charging Power": "PV1 Charger Power",
    "PV1 Input Current": "PV1 Charger Current",
    "PV1 Input Voltage": "PV1 Voltage",
    "PV2 Charging power": "PV2 Charger Power",
    "PV2 Input current": "PV2 Charger Current",
    "PV2 Input voltage": "PV2 Voltage",
    "Solar Feed To Grid Power": "Grid Power",
    "Today generation": "Energy Today",
    "Total generation": "Energy Total",
    # Nameplate ratings. The collector labels each with a unit, so each is a
    # reading, and none of these six is a control on this devcode: the
    # committed download's control template advertises no name for any of
    # them, and the values are the 7200 VA / 7200 W, 230 V, 31.3 A plate of
    # the SILA MAX 7200MH the report came from, against a 48 V battery.
    "AC Output Rating Active Power": "rated power",
    "AC Output Rating Apparent Power": "rated apparent power",
    "AC Output Rating Current": "rated current",
    "Battery Rating Voltage": "battery rated voltage",
    "Grid Rating Current": "grid rated current",
    "Grid Rating Voltage": "grid rated voltage",
}

VALUE_TRANSFORMATIONS: dict = {}

# This collector reports both generation counters in watt-hours while the
# sensors publish kilowatt-hours, so two AXPERT MAX II 10 kW inverters showed
# 8466 kWh generated today and 15045200 kWh in their lifetime (#71). The
# collector labels both readings "Wh" and the registry scales from that label;
# these entries only state what the download showed, for a payload that sends
# the value without the unit. Unlike devcode 2452, whose lifetime total is
# already in kWh, both of this one's are in Wh.
SOURCE_UNITS: dict[str, str] = {
    "Energy Today": "Wh",
    "Energy Total": "Wh",
}

# Setpoints this collector returns among the telemetry. Each is the value of a
# control the same device advertises, usually under a different spelling, and
# the committed download shows the two agreeing: Battery Re-Charge Voltage
# 44.0 V against "Back to Grid Voltage" 44.0, Battery Re-Discharge Voltage
# 48.0 V against "Back to Discharge Voltage" 48.0, Battery Bulk Voltage 58.6 V
# against "Bulk Charging Voltage", Battery Float Voltage 58.6 V against "Float
# Charging Voltage", Max AC Charging Current 30.0 A against "Max. AC Charging
# Current" and Max Charging Current 80.0 A against "Max. Charging Current".
# A sensor for any of them would be a second entity for one setting.
#
# The two the vendor spells as ratings are settings too, which is why they are
# here rather than among the rating sensors above. "AC Output Rating Voltage"
# reads 230.0 V against an "Output Voltage" control offering 110 to 240, and
# "AC Output Rating Frequency" reads 50.0 Hz against an "Output Frequency"
# control offering 50 or 60: both move when the owner changes the setting, so
# a sensor called Rated Voltage or Rated Frequency would describe the hardware
# while reporting a preference. Devcode 2451 declares the voltage the same way
# and maps the frequency, on a download that is not committed and cannot be
# re-read; this profile states what its own evidence shows.
#
# Battery Type and AC Input Range carry no unit, so they were never counted
# among the missing readings, but they are the same thing: the readback of
# "Battery Type" (Lib) and "AC Input Range" (UPS) on this device.
SETTING_READINGS: set[str] = {
    "AC Input Range",
    "AC Output Rating Frequency",
    "AC Output Rating Voltage",
    "Battery Bulk Voltage",
    "Battery Float Voltage",
    "Battery Re-Charge Voltage",
    "Battery Re-Discharge Voltage",
    "Battery Type",
    "Max AC Charging Current",
    "Max Charging Current",
}

# Which local PI30 option each of this platform's option codes means.
#
# This collector offers its selection codes as numbers above 12288, and they
# are not an enumeration: each one is the two ASCII digits of the inverter's
# own PI30 parameter read as a big-endian 16-bit integer. "00" is 0x3030 =
# 12336, "01" is 12337, "02" is 12338, and the same rule decodes the other
# option lists in the committed download - AC Input Range at 12336 and 12337
# for PGR00 and PGR01, Battery Type from 12336 for PBT00, and Output
# Frequency at 13616 and 13872, which are "50" and "60".
#
# Every label agrees with the code that rule produces: 12338 is POP02, the
# SBU order the vendor spells "Solar Bat Utility", and the reporter in #87
# watched the inverter move to battery about ten seconds after that write
# went through the cloud. The local link refused 12338 outright - "this
# inverter accepts 0, 1, 2" - which is also what confirms that the cloud
# control and the PI30 command are paired by name on this devcode.
#
# The charger list starts at 12337, so it decodes to PCP01, PCP02 and PCP03,
# and those are exactly the three the labels name; PCP00, utility first, is
# the one the platform does not offer. Its cloud control is spelled "Charging
# Source Priority" against the command's "Charger Source Priority", so
# nothing pairs the two yet and this vocabulary waits for a download that
# shows the local side (#87).
LOCAL_CONTROL_OPTION_VALUES: dict[str, dict[str, str]] = {
    "bse_output_source_priority": {"12336": "0", "12337": "1", "12338": "2"},
    "bat_charging_source": {"12337": "1", "12338": "2", "12339": "3"},
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "source_units": SOURCE_UNITS,
    "setting_readings": SETTING_READINGS,
    "local_control_option_values": LOCAL_CONTROL_OPTION_VALUES,
}
