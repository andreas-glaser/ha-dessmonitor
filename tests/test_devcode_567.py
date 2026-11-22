"""Sensor mappings for devcode 567, from the diagnostics download in #89.

A 10 kW 400 V three-phase on-grid inverter with four trackers and twenty
strings, reported through ShineMonitor. 57 of its 68 readings resolved to
nothing, including every one that carries a unit: the whole AC side, all four
trackers, all twenty strings and both energy counters.

The reason the owner opened the issue is the one these tests pin first. This
devcode leaves the plant summary's outpower, energyToday and energyTotal at
0.0000 while reporting the real figures itself, so Output Power and both
energy sensors read zero on a working inverter.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

DEVCODE = 567


def _resolved_key(title: str, unit: str = "") -> str | None:
    """Return the sensor key a raw title reaches through this devcode."""
    mapped = apply_devcode_transformations(
        DEVCODE, {"title": title, "val": "1", "unit": unit}
    )
    return resolve_sensor_key(mapped.get("title"), title)


@pytest.mark.parametrize(
    "title,expected_key",
    [
        # The readings the owner reported as stuck at zero.
        ("AC Active Power", "Output Active Power"),
        ("Daily power generation", "Energy Today"),
        ("Cumulative power generation", "Energy Total"),
        # The summary fields that were publishing that zero, onto the same
        # sensors, so the merge drops them rather than adding a second entity.
        ("outpower", "Output Active Power"),
        ("energyToday", "Energy Today"),
        ("energyTotal", "Energy Total"),
        # Three-phase AC.
        ("Grid AB Line Voltage", "Grid L1-L2 Voltage"),
        ("Grid BC Line Voltage", "Grid L2-L3 Voltage"),
        ("Grid CA Line Voltage", "Grid L3-L1 Voltage"),
        ("Grid A Phase Current (Ia)", "Grid L1 Current"),
        ("Grid B Phase Current (Ib)", "Grid L2 Current"),
        ("Grid C Phase Current (Ic)", "Grid L3 Current"),
        ("Grid Frequency", "Grid Frequency"),
        ("AC Reactive Power", "Output Reactive Power"),
        ("Power Factor", "Power Factor"),
        # DC side, per tracker and in total.
        ("DC Input Power", "PV Power"),
        ("MPPT1 input voltage", "PV1 Voltage"),
        ("MPPT4 input voltage", "PV4 Voltage"),
        ("MPPT1 Input Power", "MPPT1 Power"),
        ("MPPT4 Input Power", "MPPT4 Power"),
        ("String01 Input Current", "String01 Current"),
        ("String20 Input Current", "String20 Current"),
        # DC link and diagnostics.
        ("bus voltage", "Bus Voltage"),
        ("Positive bus voltage", "Positive Bus Voltage"),
        ("Internal Temperature", "Inside Temperature"),
        ("Inverter Efficiency", "Inverter Efficiency"),
        ("Insulation Resistance", "Insulation Resistance"),
        ("Daily Running Time", "Daily Running Time"),
        ("Cumulative Running Time", "Operating Time"),
        ("CO2 Reduction", "CO2 Reduction"),
        # Status words, two separate states.
        ("Inverter status", "Inverter Status"),
        ("Inverter Switch Status", "Inverter Switch Status"),
        ("PID status", "PID Status"),
        # Nameplate.
        ("Rated power", "rated power"),
        ("Rated voltage", "rated voltage"),
    ],
)
def test_titles_resolve_to_their_sensor(title: str, expected_key: str) -> None:
    assert _resolved_key(title) == expected_key


@pytest.mark.parametrize(
    "title",
    [
        "Inverter Boot Time",
        "Inverter Shutdown Time",
        "Software version_DC_AC",
        "Software version_FPGA",
        "Parameter version_DC_DC",
        "Communication protocol version",
        "Device e-SN",
    ],
)
def test_identity_and_firmware_fields_stay_unmapped(title: str) -> None:
    """None carries a unit, so none counts as a reading reaching no entity.

    The single Software version key cannot hold four firmware strings and
    choosing one of the four would be arbitrary.
    """
    assert _resolved_key(title) is None


def test_every_reading_that_carries_a_unit_reaches_a_sensor() -> None:
    """The whole download, as the owner's second capture reported it.

    This is the check devcode 6514 did not have when it shipped mapping its
    state of charge and nothing else (#35, then #56).
    """
    titles_with_units = [
        ("MPPT1 input voltage", "V"),
        ("MPPT2 input voltage", "V"),
        ("MPPT3 input voltage", "V"),
        ("MPPT4 input voltage", "V"),
        *((f"String{number:02d} Input Current", "A") for number in range(1, 21)),
        ("MPPT1 Input Power", "kW"),
        ("MPPT2 Input Power", "kW"),
        ("MPPT3 Input Power", "kW"),
        ("MPPT4 Input Power", "kW"),
        ("Grid AB Line Voltage", "V"),
        ("Grid BC Line Voltage", "V"),
        ("Grid CA Line Voltage", "V"),
        ("Grid A Phase Current (Ia)", "A"),
        ("Grid B Phase Current (Ib)", "A"),
        ("Grid C Phase Current (Ic)", "A"),
        ("Grid Frequency", "Hz"),
        ("bus voltage", "V"),
        ("Positive bus voltage", "V"),
        ("AC Active Power", "kW"),
        ("AC Reactive Power", "kVar"),
        ("DC Input Power", "kW"),
        ("Inverter Efficiency", "%"),
        ("Internal Temperature", "°C"),
        ("Insulation Resistance", "KΩ"),
        ("Daily power generation", "kWh"),
        ("Cumulative power generation", "kWh"),
        ("CO2 Reduction", "kg"),
        ("Daily Running Time", "Hour"),
        ("Cumulative Running Time", "Hour"),
        ("Rated power", "kW"),
        ("Rated voltage", "V"),
    ]

    unresolved = [
        title for title, unit in titles_with_units if not _resolved_key(title, unit)
    ]

    assert unresolved == []


def _sensor_for(hass, point: dict[str, Any]):
    """Build the single entity this collector would publish for one reading."""
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
    return sensor


def test_the_output_power_arrives_in_watts(hass) -> None:
    """0.95 kW on a watt sensor, which read 0.95 W before #89."""
    sensor = _sensor_for(
        hass, {"title": "AC Active Power", "val": "0.95", "unit": "kW"}
    )

    assert sensor.name == "Roof Output Power"
    assert sensor.native_unit_of_measurement == "W"
    assert sensor.native_value == 950.0


def test_the_nameplate_rating_arrives_in_watts(hass) -> None:
    """The reading in the issue title: 10 kW published as 10.0 W."""
    sensor = _sensor_for(hass, {"title": "Rated power", "val": "10", "unit": "kW"})

    assert sensor.name == "Roof Rated Power"
    assert sensor.native_unit_of_measurement == "W"
    assert sensor.native_value == 10000.0


def test_the_lifetime_counter_is_left_in_kilowatt_hours(hass) -> None:
    """It is already in the sensor's own unit, and must not be scaled."""
    sensor = _sensor_for(
        hass,
        {"title": "Cumulative power generation", "val": "24096.62", "unit": "kWh"},
    )

    assert sensor.name == "Roof Energy Total"
    assert sensor.native_unit_of_measurement == "kWh"
    assert sensor.native_value == 24096.62


def test_the_carbon_figure_is_published_in_tonnes_unscaled(hass) -> None:
    """The collector labels its own tonnes "kg", and the figure is kept.

    It is the lifetime counter times 0.997 divided by a thousand, and the
    owner's app read 24024.3 kg against 24096.6 kWh for the same moment, so
    the sensor publishes tonnes (#89). The label disagrees with the sensor's
    unit, which is exactly the shape ``_UNIT_SCALES`` converts: adding a
    ``("kg", "t")`` pair to that table would divide this by a thousand again.
    """
    sensor = _sensor_for(hass, {"title": "CO2 Reduction", "val": "24.02", "unit": "kg"})

    assert sensor.name == "Roof CO2 Reduction"
    assert sensor.native_unit_of_measurement == "t"
    assert sensor.native_value == 24.02


def test_a_string_current_reaches_its_own_sensor(hass) -> None:
    sensor = _sensor_for(
        hass, {"title": "String07 Input Current", "val": "1.59", "unit": "A"}
    )

    assert sensor.name == "Roof String 07 Current"
    assert sensor.native_unit_of_measurement == "A"
    assert sensor.native_value == 1.59


def test_the_switch_status_publishes_the_word_the_vendor_sent(hass) -> None:
    """A state word offered to float() is discarded in silence (#81)."""
    sensor = _sensor_for(
        hass,
        {"title": "Inverter Switch Status", "val": "On-grid operation", "unit": ""},
    )

    assert sensor.native_value == "On-grid operation"


def test_the_zero_summary_figure_does_not_publish_a_second_entity(hass) -> None:
    """Why the owner saw 0.0 kW beside a working inverter.

    The summary title and the device's own reading reach one sensor key, so
    the merge drops the summary point rather than publishing a second entity
    under the same name with the vendor's unset 0.0000 in it (#58, #75).
    """
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": DEVCODE, "alias": "Roof"},
                "data": [
                    {"title": "AC Active Power", "val": "0.95", "unit": "kW"},
                    {"title": "outpower", "val": "0.0000", "unit": "kW"},
                ],
            }
        },
    )

    entities = _build_sensor_entities(coordinator, set())

    assert [entity.name for entity in entities] == ["Roof Output Power"]
    assert entities[0].native_value == 950.0
