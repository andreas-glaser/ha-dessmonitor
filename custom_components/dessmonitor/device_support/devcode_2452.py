"""Eybond Data Collector (devcode 2452).

Axpert-family PI18 inverter on the DessMonitor platform. Evidence for the
rating and setting titles below is the diagnostics download in
``docs/evidence/devcodes/analysis_2452.json`` (#53).

``queryDeviceLastData`` returns the inverter's nameplate ratings and its own
setpoints alongside the live readings. The ratings are facts about the hardware
and become diagnostic sensors; the setpoints are settings, five of which the
account already publishes as number and select entities, so they are declared
in ``SETTING_READINGS`` rather than mapped onto a sensor each. Without that the
support report counted all fourteen as readings that reach no entity and told
the owner readings were missing when none were.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2452)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": ["Axpert (PI18 protocol, rebranded)"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "Solar-Utility-Battery": "Solar → Utility → Battery",
    "Solar-Battery-Utility": "Solar → Battery → Utility",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "Solar first": "PV First",
    "Solar and Utility": "PV Is At The Same Level As Utility",
    "Only solar": "Only PV",
}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Output Frequency": "Output Frequency",
    "AC output active power": "Output Active Power",
    "AC output apparent power": "Output Apparent Power",
    "AC output voltage": "Output Voltage",
    "Battery Capacity": "State of Charge",
    "Battery Discharging Current": "Battery Discharge Current",
    "Grid voltage": "Grid Voltage",
    "Output load percent": "Load Percent",
    "PV1 Input Power": "PV1 Charger Power",
    "PV1 Input voltage": "PV1 Voltage",
    "PV2 Input Power": "PV2 Charger Power",
    "Today generation": "Energy Today",
    "Total generation": "Energy Total",
    "Month generation": "Energy Month",
    "Year generation": "Energy Year",
    "Second AC output frequency": "Second Output Frequency",
    "Second AC output voltage": "Second Output Voltage",
    # Nameplate ratings. The collector labels each with a unit, so each is a
    # reading, and none of them is a control on this devcode.
    "AC output rating active power": "rated power",
    "AC output rating apparent power": "rated apparent power",
    "AC Output Rating Current": "rated current",
    "AC rated frequency": "rated frequency",
    "Battery Rating Voltage": "battery rated voltage",
    "Grid Rating Current": "grid rated current",
    # Summary endpoint (webQueryDeviceEs) returns energyToday/energyTotal
    # alongside the lastData-sourced Today/Total generation. Map them to
    # the same canonical names so the coordinator's summary-dedup logic
    # recognises them as duplicates and skips them.
    "energyToday": "Energy Today",
    "energyTotal": "Energy Total",
}


def _wh_to_kwh(value):
    """Convert raw Wh value to kWh. Returns original value on parse failure."""
    try:
        return float(value) / 1000
    except (TypeError, ValueError):
        return value


# queryDeviceLastData reports Today/Month/Year generation in Wh while the
# sensor unit is fixed to kWh, so scale them here. Total generation is
# already in kWh (matches parameters API and summary endpoint) and is
# intentionally left alone.
VALUE_TRANSFORMATIONS: dict = {
    "Energy Today": _wh_to_kwh,
    "Energy Month": _wh_to_kwh,
    "Energy Year": _wh_to_kwh,
}

PARAMETER_SENSOR_NAMES: set[str] = set()

# Setpoints this collector returns among the telemetry. The first five are the
# values of controls the account publishes as number and select entities, so a
# sensor for them would be a second entity for one setting; the last three are
# settings the control template on the account in #53 does not advertise, and a
# setting is not a reading whichever way the vendor delivers it.
SETTING_READINGS: set[str] = {
    "AC Output Rating Voltage",
    "Back To Discharge Voltage",
    "Battery bulk voltage",
    "Battery float voltage",
    "Battery recharge voltage",
    "Battery under voltage",
    "Low DC cut off voltage on second output",
    "Setting discharge time on the 2nd output",
    "Scheduled time for 2nd AC output on",
    "Scheduled time for 2nd AC output off",
    "Whether the second route is enabled",
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "setting_readings": SETTING_READINGS,
}
