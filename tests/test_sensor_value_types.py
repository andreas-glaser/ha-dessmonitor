"""Every sensor key is coerced as the kind of value it carries.

``sensor.py`` decides between an enumeration, free-form text and a number from
two sets of keys. A key that carries text and appears in neither set is offered
to ``float()`` and discarded, so the entity reads unknown for ever and nothing
in the log says why: that is how the four per-subsystem status sensors shipped
(#81). These tests pin the behaviour and fail on the next undeclared one.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.sensor import (
    ENUM_SENSOR_TITLES,
    TEXT_SENSOR_TITLES,
    DessMonitorSensor,
)

# A key with no unit, no device class and no state class measures nothing, so
# its value is a word rather than a number. Each one is declared as an
# enumeration or as text; this names the exceptions and why they are exceptions.
#
# "Software version" is numeric today. A collector that answers "V1.08" already
# reads unknown on it, but one that answers "1.080" publishes 1.08, and moving
# the key to text would change that state to "1.080" on an installation that
# has the sensor. It is a change to what an existing install publishes rather
# than an addition, so it is tracked separately (#84).
_NUMERIC_WITHOUT_A_UNIT = {"Software version"}


def _sensor(title: str, value: Any, devcode: int = 6416) -> DessMonitorSensor:
    """Create one sensor over the smallest coordinator surface that works."""
    serial = "TEST-SERIAL"
    data_point = {"title": title, "val": value}
    payload: dict[str, Any] = {
        "device": {"alias": "Test inverter", "devcode": devcode},
        "collector": {"pn": "TEST-COLLECTOR"},
        "data": [data_point],
    }
    coordinator = MagicMock()
    coordinator.data = {serial: payload}
    return DessMonitorSensor(
        coordinator=coordinator,
        device_sn=serial,
        device_meta=payload["device"],
        collector_meta=payload["collector"],
        sensor_type=title,
        data_point=data_point,
    )


def test_every_unitless_sensor_key_declares_how_it_is_read() -> None:
    """Fail when a key that carries a word is read as a number."""
    undeclared = sorted(
        key
        for key, config in SENSOR_TYPES.items()
        if not config.get("unit")
        and not config.get("device_class")
        and not config.get("state_class")
        and key not in ENUM_SENSOR_TITLES
        and key not in TEXT_SENSOR_TITLES
        and key not in _NUMERIC_WITHOUT_A_UNIT
    )
    assert not undeclared, (
        f"these sensor keys measure nothing and are read as numbers: "
        f"{undeclared}. A vendor's word for a state cannot survive float(), "
        "so the entity reads unknown. Add each one to TEXT_SENSOR_TITLES or "
        "ENUM_SENSOR_TITLES in sensor.py."
    )


@pytest.mark.parametrize(
    ("title", "value"),
    [
        # The vocabulary the Voltronic-family collectors send, from the
        # downloads in docs/evidence/devcodes (#61, #81).
        ("Battery Status", "Battery Discharge"),
        ("Battery Status", "Charging Batteries"),
        ("PV Status", "PV Undervoltage"),
        ("Grid Status", "Mains OK"),
        ("Load Status", "Load On (Normal)"),
        ("Inverter Status", "Normal"),
    ],
)
def test_a_status_reading_publishes_the_vendors_own_words(
    title: str, value: str
) -> None:
    assert _sensor(title, value).native_value == value


def test_a_status_reading_the_collector_leaves_empty_reads_unknown() -> None:
    assert _sensor("Grid Status", "").native_value is None
