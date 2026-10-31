"""Sensor mappings for devcode 4743, from the redacted analysis in #58.

The collector reports a single-phase grid-connected PV inverter. Before the
profile existed, 3 of its 47 titles resolved: both energy counters were dropped
in silence, which is why the reporter saw 0.00 kWh while the app showed 10.2
and 4172.5 kWh.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.device_support import apply_devcode_transformations
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

DEVCODE = 4743


def _resolved_key(title: str) -> str | None:
    """Return the sensor key a raw title reaches through this devcode."""
    mapped = apply_devcode_transformations(DEVCODE, {"title": title, "val": "1"})
    return resolve_sensor_key(mapped.get("title"), title)


@pytest.mark.parametrize(
    "title,expected_key",
    [
        # The two readings the issue was opened for.
        ("PV power generation today", "Energy Today"),
        ("Total photovoltaic power generation", "Energy Total"),
        # The AC grid readings the reporter asked for by name.
        ("Inverter R-phase voltage", "Grid Voltage"),
        ("Inverter R-phase current", "grid current"),
        ("Inverter R-phase frequency", "Grid Frequency"),
        ("Inverter R-phase power H", "Grid Power"),
        ("Inverter three-phase power H", "Output Active Power"),
        ("Inverter three-phase reactive power H", "Output Reactive Power"),
        ("Inverter power factor", "Power Factor"),
        ("Load R-phase voltage", "Output Voltage"),
        ("Three-phase total load power H", "PLoad"),
        # Strings and the DC bus.
        ("Total PV power", "PV Power"),
        ("PV1 voltage", "PV1 Voltage"),
        ("PV3 voltage", "PV3 Voltage"),
        ("PV1 current", "PV1 Current"),
        ("PV3 power", "PV3 Power"),
        ("bus voltage", "Bus Voltage"),
        ("Positive bus voltage", "Positive Bus Voltage"),
        ("Negative bus voltage", "Negative Bus Voltage"),
        # Temperatures, whose vendor titles are shorter than elsewhere.
        ("InverterTemp", "INV Module Termperature"),
        ("DC Temp", "DC Module Termperature"),
    ],
)
def test_titles_resolve_to_their_sensor(title: str, expected_key: str) -> None:
    assert _resolved_key(title) == expected_key


def test_total_pv_power_stays_in_watts() -> None:
    """Without the mapping this title lands on a kilowatt sensor.

    ``outpower`` carries the friendly name "Total PV Power" and is defined in
    kW, so the raw title resolves onto it by name and a 1552 W reading would be
    published as 1552 kW.
    """
    assert resolve_sensor_key("Total PV power") == "outpower"
    assert SENSOR_TYPES["outpower"]["unit"] == "kW"

    assert _resolved_key("Total PV power") == "PV Power"
    assert SENSOR_TYPES["PV Power"]["unit"] == "W"


@pytest.mark.parametrize(
    "title,unit,expected_name,expected_unit",
    [
        ("PV power generation today", "kWh", "Energy Today", "kWh"),
        ("Total photovoltaic power generation", "kWh", "Energy Total", "kWh"),
        ("Inverter R-phase voltage", "V", "Grid Voltage", "V"),
        ("Total PV power", "W", "Solar Power", "W"),
        ("InverterTemp", "°C", "Inverter Temperature", "°C"),
    ],
)
def test_entities_publish_the_expected_unit(
    hass, title: str, unit: str, expected_name: str, expected_unit: str
) -> None:
    """A mapped reading reaches Home Assistant with the vendor's own unit."""
    point: dict[str, Any] = {"title": title, "val": "1.0", "unit": unit}
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": DEVCODE, "alias": "Roof"},
                "data": [point],
            }
        },
    )

    (sensor,) = _build_sensor_entities(coordinator, set())

    assert sensor.name == f"Roof {expected_name}"
    assert sensor.native_unit_of_measurement == expected_unit


def test_battery_readings_are_not_claimed() -> None:
    """This collector reports no battery, so it declares no battery mappings."""
    from custom_components.dessmonitor.device_support.devcode_4743 import (
        DEVCODE_CONFIG,
    )

    assert DEVCODE_CONFIG["charger_priority_mapping"] == {}
    assert DEVCODE_CONFIG["output_priority_mapping"] == {}
    assert DEVCODE_CONFIG["operating_mode_mapping"] == {}
