"""When a device last reported something new, and how that is measured.

The vendor cloud answers with the reading it stored before a collector went
quiet, so a successful refresh is no evidence that the numbers are current and
nothing in the payload says otherwise (#78). These hold the one signal that
exists for it: a diagnostic sensor carrying when the payload's own timestamp
last moved, measured on this host's clock, with no existing entity's
availability touched.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from custom_components.dessmonitor.sensor import (
    LAST_READING_KEY,
    DessMonitorLastReadingSensor,
    _build_sensor_entities,
)

SERIAL = "TEST-SERIAL"


def _payload(stamp: str | None, *, battery: str = "53.1") -> dict[str, Any]:
    """One device's payload, with or without the vendor's own timestamp."""
    points: list[dict[str, Any]] = [
        {"title": "Battery Voltage", "val": battery, "unit": "V"},
        {"title": "Data Source", "val": "Cloud", "unit": ""},
    ]
    if stamp is not None:
        points.append({"title": "Timestamp", "val": stamp, "unit": ""})
    return {
        SERIAL: {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"alias": "Test inverter", "devcode": 6515, "devaddr": 1},
            "data": points,
        }
    }


def _sensor(coordinator: MagicMock) -> DessMonitorLastReadingSensor:
    device = coordinator.data[SERIAL]
    return DessMonitorLastReadingSensor(
        coordinator=coordinator,
        device_sn=SERIAL,
        device_meta=device["device"],
        collector_meta=device["collector"],
    )


def test_the_sensor_is_a_diagnostic_timestamp() -> None:
    """It reports a point in time on this host's clock, not a measurement."""
    coordinator = MagicMock()
    coordinator.data = _payload("2026-11-16 18:26:52")

    sensor = _sensor(coordinator)

    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.native_unit_of_measurement is None
    assert sensor.unique_id == f"{SERIAL}_last_reading_received"


def test_a_frozen_timestamp_holds_the_state_still() -> None:
    """The condition the sensor exists for.

    The cloud keeps answering with the stored payload, so the refresh
    succeeds and nothing else in Home Assistant changes. The state stays
    where it was, and the age it implies grows on its own.
    """
    coordinator = MagicMock()
    coordinator.data = _payload("2026-11-16 18:26:52")
    sensor = _sensor(coordinator)
    sensor.hass = MagicMock()
    sensor.async_write_ha_state = MagicMock()
    first = sensor.native_value

    sensor._handle_coordinator_update()

    assert sensor.native_value == first
    assert sensor.extra_state_attributes["payload_timestamp"] == "2026-11-16 18:26:52"
    # Nothing has been seen to move yet, so the state is when this integration
    # started watching rather than when the device reported.
    assert sensor.extra_state_attributes["observed_change"] is False


def test_a_new_reading_advances_the_state() -> None:
    """A collector's next frame is what the sensor is waiting for."""
    coordinator = MagicMock()
    coordinator.data = _payload("2026-11-16 18:26:52")
    sensor = _sensor(coordinator)
    sensor.hass = MagicMock()
    sensor.async_write_ha_state = MagicMock()
    before = sensor.native_value

    coordinator.data = _payload("2026-11-16 18:39:57", battery="53.4")
    sensor._handle_coordinator_update()

    assert sensor.native_value > before
    assert sensor.extra_state_attributes["payload_timestamp"] == "2026-11-16 18:39:57"
    assert sensor.extra_state_attributes["observed_change"] is True
    assert sensor.native_value - before < timedelta(minutes=1)


def test_a_changed_reading_under_a_held_timestamp_is_not_movement() -> None:
    """The timestamp is the signal, deliberately, and not the values.

    A payload whose figures differ while its own timestamp stands still is
    what the platform answers for a collector that has gone quiet; treating a
    changed figure as a new reading would report every such device as fresh.
    """
    coordinator = MagicMock()
    coordinator.data = _payload("2026-11-16 18:26:52")
    sensor = _sensor(coordinator)
    sensor.hass = MagicMock()
    sensor.async_write_ha_state = MagicMock()
    before = sensor.native_value

    coordinator.data = _payload("2026-11-16 18:26:52", battery="51.0")
    sensor._handle_coordinator_update()

    assert sensor.native_value == before
    assert sensor.extra_state_attributes["observed_change"] is False


def test_one_sensor_is_added_per_device_and_only_once() -> None:
    """It is additive: one diagnostic entity beside the readings' own."""
    coordinator = MagicMock()
    coordinator.data = _payload("2026-11-16 18:26:52")
    known: set[str] = set()

    entities = _build_sensor_entities(coordinator, known)

    kinds = [getattr(entity, "_sensor_type", None) for entity in entities]
    assert kinds.count(LAST_READING_KEY) == 1
    assert "Battery Voltage" in kinds

    assert _build_sensor_entities(coordinator, known) == []


def test_a_payload_with_no_timestamp_gets_no_sensor() -> None:
    """Nothing to watch means no entity, rather than one that cannot move."""
    coordinator = MagicMock()
    coordinator.data = _payload(None)

    entities = _build_sensor_entities(coordinator, set())

    kinds = [getattr(entity, "_sensor_type", None) for entity in entities]
    assert LAST_READING_KEY not in kinds
