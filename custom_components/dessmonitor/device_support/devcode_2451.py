"""Eybond Data Collector (devcode 2451).

Axpert-family inverter on the DessMonitor platform, closely related to devcode
2449 and sharing devcode 2452's "Rating" spellings for its nameplate fields.
Evidence is the diagnostics download in
``docs/evidence/devcodes/analysis_2451.json`` (#74).

``queryDeviceLastData`` returns the inverter's nameplate ratings and its own
setpoints alongside the live readings. The ratings are facts about the hardware
and become diagnostic sensors; the setpoints are settings the account publishes
as number and select entities, so they are declared in ``SETTING_READINGS``.
Of the 49 readings this collector sent, 25 reached an entity and the report
told the owner that sixteen were missing.

As on devcode 2452, the output rating voltage tracks the writable Output
Voltage setting rather than describing the hardware, so it is declared a
setting rather than mapped onto a rating sensor.

The collector's reading titles and its control-field names are not spelled the
same - it reports "Battery Bulk Voltage" as a reading against a "Bulk Charging
Voltage" control, and "Battery Re-Charge Voltage" against "Back to Grid
Voltage" - so a setting is declared from the reading title it sends.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 2451)",
    "description": "Eybond data collector/gateway",
    "manufacturer": "Eybond",
    "known_inverters": ["Axpert MKS IV 5600VA", "Mecer Axpert MKS IV 5600VA"],
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
    "Utility First": "Utility First",
    "Solar First": "PV First",
    "Solar + Utility": "PV Is At The Same Level As Utility",
    "Only Solar Charging Permitted": "Only PV",
}

OPERATING_MODE_MAPPING: dict[str, str] = {}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    "AC Output Active Power": "Output Active Power",
    "AC1 Output Apparent Power": "Output Apparent Power",
    "AC1 Output Frequency": "Output Frequency",
    "AC1 Output Voltage": "Output Voltage",
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
    # Real readings this collector sends that reached no entity (#74).
    "Grid Input Current": "grid current",
    "Battery Voltage From SCC": "Battery Voltage From SCC",
    # Nameplate ratings. The collector labels each with a unit, so each is a
    # reading, and none of them is a control on this devcode.
    "AC Output Rating Active Power": "rated power",
    "AC Output Rating Apparent Power": "rated apparent power",
    "AC Output Rating Current": "rated current",
    "AC Output Rating Frequency": "rated frequency",
    "Battery Rating Voltage": "battery rated voltage",
    "Grid Rating Current": "grid rated current",
    "Grid Rating Voltage": "grid rated voltage",
}

# Setpoints this collector returns among the telemetry, each the value of a
# control the account publishes. A setting is not a reading whichever way the
# vendor delivers it, and counting these as dropped readings is what told this
# owner sixteen readings were missing (#74).
SETTING_READINGS: set[str] = {
    "AC Input Range",
    # Tracks the writable Output Voltage setting, as on devcode 2452.
    "AC Output Rating Voltage",
    "Battery Bulk Voltage",
    "Battery Float Voltage",
    "Battery Re-Charge Voltage",
    "Battery Re-Discharge Voltage",
    "Battery Type",
    "Max AC Charging Current",
    "Max Charging Current",
}

VALUE_TRANSFORMATIONS: dict = {}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "setting_readings": SETTING_READINGS,
}
