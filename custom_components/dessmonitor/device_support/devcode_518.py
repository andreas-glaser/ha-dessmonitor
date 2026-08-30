"""Solar grid-tie inverter (devcode 518).

Single-/three-phase string inverter reported by SmartClient/SmartESS accounts
(e.g. Q0025-series data loggers). queryDeviceLastData returns lower-cased,
spelled-out field titles ("active power", "total energy", "today energy") that
do not match the integration's canonical sensor names, so without this mapping
the energy and power sensors stay at 0 even though the data is present.

Field titles captured from a live devcode 518 inverter (BRAZIL-H grid profile).
"""

from __future__ import annotations

DEVICE_INFO = {
    "name": "Solar Grid-Tie Inverter (devcode 518)",
    "description": "String PV grid-tie inverter",
    "manufacturer": "Eybond",
    "known_inverters": ["Q0025-series"],
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
    "current year generating capacity": "Energy Year",
    "grid frequency": "Grid Frequency",
    "inverter temperature": "INV Module Termperature",
    "DC voltage 1": "PV1 Voltage",
    "DC current 1": "PV1 Charger Current",
    "DC voltage 2": "PV2 Voltage",
    "DC current 2": "PV2 Charger Current",
    "apparent power value": "Output Apparent Power",
}

DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
}
