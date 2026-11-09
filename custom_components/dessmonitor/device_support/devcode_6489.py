"""Eybond Data Collector (devcode 6489).

JSD Solar 5.5 kW 48 V hybrid inverter behind a ``WFBLE.RTU.Bar`` collector on
firmware 7.6.5.11, reported through the DessMonitor platform. Every mapping
below comes from the redacted diagnostics download in
``docs/evidence/devcodes/analysis_6489.json`` (#66), which resolved 21 of 71
titles and dropped 40 that carry a unit.

The collector sends the same reading twice. It leads with a short dashboard
block - output voltage, output current percentage, input frequency, rated
voltage, frequency - and then repeats the measurements in full sections for the
mains, the battery, the AC output, the PV input and the BMS. ``Output voltage``
appears in both blocks (230.1 V and 230.0 V in the download), which is what
establishes the duplication, and ``Input frequency`` is read as the dashboard
copy of ``Mains frequency`` on the same evidence: both read 0.00 with the mains
absent. ``frequency`` is the one dashboard field with no counterpart in the
detailed sections, and it reads the nominal 50.0 beside ``Rated voltage``
230.0 while the measured output frequency reads 49.90, so it is the rated
frequency.

The three energy pairs are placed by the section they arrive in rather than by
their wording, which is ambiguous: ``Total electricity consumption`` closes the
mains section, ``Total output electricity consumption`` the AC output section,
and ``Total photovoltaic power generation`` the PV section. The last pair is
the account's PV generation, so it maps onto Energy Today and Energy Total,
which also lets the summary endpoint's ``energyToday`` and ``energyTotal`` be
recognised as the same sensors rather than published a second time.

``Charging voltage`` and ``Charging current`` are measurements, not the charger
setpoints beside them: both read 0.0 in the download while ``Charge Mode``
reads "Stop charging" and the CV, float and equalization setpoints read 56.4,
55.2 and 58.4 V.

Left unmapped on purpose:

- ``BMS status`` (0.0), ``BMS fault code`` and ``BMS warning code`` (both 0)
  are raw words with no unit. Decoding them needs this BMS's fault table,
  which no report carries, and a sensor per word would publish numbers nobody
  can read.
- ``DCDC control status`` ("Discharge soft start") is an internal state of the
  DC-DC stage. It is readable English, so it can become a text sensor the
  moment someone wants it; nothing in the download says what its full set of
  strings is.
- ``id`` and ``Timestamp`` are the payload's own identity fields.

The control template advertises fourteen fields and needs no mappings: the
names are already readable. Two of them are left for the reporter to settle.
``system time`` and ``Power generation statistics time`` are clock-shaped, and
the download caught their reads still in progress, so neither format has been
observed; until one is, ``TEMPORAL_CONTROLS`` cannot declare them without
guessing at a write that sets the inverter's clock.
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Eybond Data Collector (devcode 6489)",
    "description": (
        "Data collector/gateway for single-phase hybrid inverters with a "
        "lithium BMS link, reported through DessMonitor"
    ),
    "manufacturer": "Eybond",
    "known_inverters": ["JSD Solar 5.5 kW 48 V hybrid"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}

# This collector reports no priority readings. Both priorities reach Home
# Assistant as select entities, which take their labels from the control
# template's own option list ("Mains output is preferred" and the rest).
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {}

# "Battery mode" is the only value the download observed, taken while the mains
# was absent. Any other string this collector uses reads as unavailable until
# it is registered here, so the rest wait on a download taken with the mains
# present rather than on a guess at the vendor's wording.
OPERATING_MODE_MAPPING: dict[str, str] = {
    "Battery mode": "Battery",
}

SENSOR_TITLE_MAPPINGS: dict[str, str] = {
    # Mains section. The parameters endpoint names the voltage gd_grid_voltage.
    "Mains input voltage": "Grid Voltage",
    "Mains frequency": "Grid Frequency",
    "Input frequency": "Grid Frequency",
    "Total electricity consumption of the day": "Daily Mains Load Energy",
    "Total electricity consumption": "Accumulated Mains Load Energy",
    # Battery section.
    "Charging voltage": "Battery Charging Voltage",
    "Charging current": "Battery Charging Current",
    # AC output section.
    "Output the total electricity consumption of the day": "Daily Load Energy",
    "Total output electricity consumption": "Accumulated Load Power",
    # PV section, which is the account's generation. The summary endpoint
    # reports the same two figures as energyToday and energyTotal: they are
    # mapped onto the same keys so that both the coordinator's summary dedup
    # and the sensor platform's recognise them as one reading. Mapped only
    # here, a device that carries both would publish two entities called
    # Energy Today, and the one the summary feeds reads 0 wherever the vendor
    # leaves that field unset (#58).
    "Total PV power generation on the day": "Energy Today",
    "Total photovoltaic power generation": "Energy Total",
    "energyToday": "Energy Today",
    "energyTotal": "Energy Total",
    # BMS section. The pack answers "--" for the two Ah figures, so they read
    # unknown on this reporter's battery; they stay mapped because another
    # pack behind the same devcode would report them.
    "BMS voltage": "BMS battery voltage",
    "BMS current": "BMS battery current",
    "BMS Temperature": "BMS battery temperature",
    "BMS SOC": "State of Charge",
    "BMS Remaining power": "BMS Remaining Capacity",
    "BMS Rating Energy": "BMS Rated Capacity",
    "BMS max change current": "BMS Max Charge Current",
    # Nameplate rating, the one dashboard field the detailed sections do not
    # repeat.
    "frequency": "rated frequency",
}

CONTROL_FIELD_MAPPINGS: dict[str, str] = {}

TEMPORAL_CONTROLS: dict[str, str] = {}

VALUE_TRANSFORMATIONS: dict = {}

PARAMETER_SENSOR_NAMES: set[str] = set()

# Setpoints this collector returns among the telemetry. Only "Maximum charging
# current" is a control the account publishes; the rest are settings its
# control template does not advertise, and a setting is not a reading
# whichever way the vendor delivers it. Counting them as readings that reach
# no entity is what tells an owner whose sensors all work that twenty are
# missing (#53, #58, #61).
SETTING_READINGS: set[str] = {
    "Balanced charging mode",
    "Battery Type",
    "Battery discharge alarm voltage",
    "Battery discharge cut-off voltage",
    "Constant voltage charging time",
    "Constant voltage charging voltage",
    "Equalization Charge Timeout",
    "Equalization charging interval",
    "Equalization charging time",
    "Equalization charging voltage",
    "Float charging voltage",
    "High frequency of mains loss",
    "High point of mains loss voltage",
    "Low frequency of mains loss",
    "Low point of mains loss voltage",
    "Low power discharge time",
    "Mains loss voltage high recovery point",
    "Mains loss voltage low recovery point",
    "Maximum charging current",
    "Number of battery cells",
}

ABSENT_READINGS: dict[str, str] = {}

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
    "absent_readings": ABSENT_READINGS,
}
