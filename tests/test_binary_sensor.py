"""What the connectivity sensor reports, and what it refuses to claim (#78).

The cloud answers ``queryDeviceLastData`` with the readings it stored before a
collector went quiet, so a payload full of measurements is not evidence that
anything is still reporting. This sensor counted those readings and therefore
read "connected" for the life of an entry, which is what the owner in #78 saw
while their collector was off the network.

The platform documents one status enumeration for collectors and devices
alike - 0 online, 1 offline, 2 fault, 3 standby, 4 warning, 5 error, 6
protocol error - and only the offline value means it has lost contact.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.binary_sensor import _build_binary_sensor_entities


def _coordinator(status=None, *, readings=True, reported=None):
    coordinator = MagicMock()
    device: dict[str, object] = {"alias": "Inverter", "devcode": 2376, "devaddr": 1}
    if status is not None:
        device["status"] = status
    coordinator.data = {
        "SERIAL": {
            "collector": {"pn": "COLLECTOR"},
            "device": device,
            "data": (
                [{"title": "Timestamp", "val": "2026-11-14 09:00:00"}]
                if readings
                else []
            ),
        }
    }
    coordinator.cloud_device_status = {} if reported is None else {"SERIAL": reported}
    return coordinator


def _status_sensor(coordinator):
    (sensor,) = _build_binary_sensor_entities(coordinator, set())
    return sensor


def test_an_account_without_a_status_field_reads_as_it_always_has() -> None:
    """Saying nothing is not saying online, but it is not a reason to flip."""
    sensor = _status_sensor(_coordinator())

    assert sensor.is_on is True
    assert "cloud_status" not in (sensor.extra_state_attributes or {})


def test_no_readings_still_reads_disconnected_without_a_status() -> None:
    assert _status_sensor(_coordinator(readings=False)).is_on is False


def test_the_platform_reporting_offline_turns_the_sensor_off() -> None:
    """The readings are still there; the platform says it is not hearing them."""
    sensor = _status_sensor(_coordinator(reported=1))

    assert sensor.is_on is False
    assert sensor.extra_state_attributes["cloud_status"] == 1
    assert sensor.extra_state_attributes["cloud_status_text"] == "offline"
    assert sensor.extra_state_attributes["last_seen"] == "2026-11-14 09:00:00"


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (0, "online"),
        (2, "fault"),
        (3, "standby"),
        (4, "warning"),
        (5, "error"),
        (6, "protocol error"),
        (9, "unknown (9)"),
    ],
)
def test_every_other_state_is_a_device_the_platform_still_hears(status, text) -> None:
    """A fault is not a disconnection, and neither is a code nobody documented."""
    sensor = _status_sensor(_coordinator(reported=status))

    assert sensor.is_on is True
    assert sensor.extra_state_attributes["cloud_status_text"] == text


def test_the_device_payload_answers_when_the_summary_did_not() -> None:
    """The summary call can fail on its own; the device list still carries it."""
    sensor = _status_sensor(_coordinator(status="1"))

    assert sensor.is_on is False
    assert sensor.extra_state_attributes["cloud_status"] == 1


def test_a_status_that_is_not_a_number_is_ignored() -> None:
    sensor = _status_sensor(_coordinator(status="online"))

    assert sensor.is_on is True
    assert "cloud_status" not in sensor.extra_state_attributes
