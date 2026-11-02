"""Value mappings for devcode 6515, from the redacted analysis in #57.

The profile shipped in v1.9.0 from the analysis in #13, taken from an ANENJI
ANJ-HHS-11KW. Nothing guarded it until a Maxsky EM11000 on the same devcode
supplied a second analysis, which is the one committed under
docs/evidence/devcodes/. Each expectation below is a value that report or its
reporter observed, including the two the reporter first saw at register level
and then checked against Home Assistant.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.device_support import apply_devcode_transformations
from custom_components.dessmonitor.device_support.device_registry import (
    map_control_field,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key


@pytest.mark.parametrize(
    "title,raw,expected",
    [
        # The operating mode this collector reports, where the ANENJI unit in
        # #13 reports OffgridMode and Battery Mode.
        ("Operating mode", "Mains Mode", "Grid Mode"),
        ("Operating mode", "OffgridMode", "Off-grid Mode"),
        ("Operating mode", "Battery Mode", "Battery Mode"),
        ("Main Output Priority", "SBU", "Solar → Battery → Utility"),
        ("Current output priority", "SUB", "Solar → Utility → Battery"),
        ("Current charging priority", "OSO", "Only Solar"),
        ("Charger Source Priority", "SOF", "Solar First"),
        # A code no evidence covers is shown as the collector sent it.
        ("Charger Source Priority", "XYZ", "XYZ"),
    ],
)
def test_observed_values_are_labelled(title: str, raw: str, expected: str) -> None:
    point = {"title": title, "val": raw, "unit": ""}
    assert apply_devcode_transformations(6515, point)["val"] == expected
    assert point["val"] == raw


@pytest.mark.parametrize(
    "title,expected_key",
    [
        # The vendor spells both temperatures with the same typo, and the
        # canonical keys carry it so that the raw title still resolves.
        ("INV Module Termperature", "INV Module Termperature"),
        ("DC Module Termperature", "DC Module Termperature"),
        ("Output Aparent Power", "Output Apparent Power"),
        ("Output frequency", "Output Frequency"),
        ("PV temperature", "PV Temperature"),
        ("PV1 Current", "PV1 Charger Current"),
        ("PV2 Power", "PV2 Charger Power"),
        ("Total PV Power", "PV Power"),
        ("Total PV Charging Power", "PV Total Charger Power"),
        ("Total PV Charging Current", "PV charging current"),
        ("Daily PV energy generation", "Energy Today"),
        ("Total PV energy generation", "Energy Total"),
        ("Load Percentage", "Load Percent"),
        # Titles that need no mapping on this devcode.
        ("Battery Current", "Battery Current"),
        ("Battery Power", "Battery Power"),
        ("SOC", "SOC"),
        ("PV1 Voltage", "PV1 Voltage"),
        ("PV2 Voltage", "PV2 Voltage"),
        ("Grid Power", "Grid Power"),
    ],
)
def test_reported_titles_resolve(title: str, expected_key: str) -> None:
    mapped = apply_devcode_transformations(6515, {"title": title}).get("title")
    assert resolve_sensor_key(mapped, title) == expected_key


def test_temperature_entities_are_named_without_the_vendor_typo(hass) -> None:
    """The canonical key keeps the typo; the name the user sees must not."""
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": 6515, "alias": "Home"},
                "data": [
                    {"title": "INV Module Termperature", "val": "47", "unit": "°C"},
                    {"title": "DC Module Termperature", "val": "42", "unit": "°C"},
                ],
            }
        },
    )

    names = {entity.name for entity in _build_sensor_entities(coordinator, set())}

    assert names == {"Home Inverter Temperature", "Home DC Module Temperature"}


def test_discharge_current_is_published_as_the_cloud_reports_it(hass) -> None:
    """The cloud already signs this reading, so nothing may re-derive it.

    The reporter first measured battery current over RS232, where -21.0 A
    arrives as the unsigned 65515, and asked whether Home Assistant needed the
    two's complement conversion. On the cloud path it does not: the API sends
    the negative value, and `local/smg.py` owns that conversion for the local
    path.
    """
    coordinator = MagicMock(
        hass=hass,
        data={
            "TEST-SN": {
                "collector": {"pn": "TEST-PN"},
                "device": {"devcode": 6515, "alias": "Home"},
                "data": [
                    {"title": "Battery Current", "val": "-0.7", "unit": "A"},
                    {"title": "Battery Power", "val": "-542", "unit": "W"},
                ],
            }
        },
    )

    values = {
        entity.name: entity.native_value
        for entity in _build_sensor_entities(coordinator, set())
    }

    assert values == {"Home Battery Current": -0.7, "Home Battery Power": -542}


def test_equalization_time_is_named_after_its_neighbours() -> None:
    """This collector reports the setting under its internal identifier.

    Reported in #57: the field arrived as `bat_eq_time` while the settings
    either side of it read "Eq charging voltage" and "Eq charging interval",
    so it published an entity under the raw identifier.
    """
    assert map_control_field(6515, "bat_eq_time") == "Eq charging time"
    assert map_control_field(6515, "Eq charging voltage") == "Eq charging voltage"


def test_control_names_are_trimmed_before_they_become_an_entity() -> None:
    """The same collector reports the clock with a leading space (#57)."""
    assert map_control_field(6515, " Inverter Time") == "Inverter Time"
