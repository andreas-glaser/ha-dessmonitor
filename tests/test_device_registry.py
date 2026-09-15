"""Device transformation and unsupported-device warning contracts."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    device_registry,
)
from custom_components.dessmonitor.sensor import async_setup_entry


@pytest.fixture(autouse=True)
def reset_warning_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep process-wide warning history independent between tests."""
    monkeypatch.setattr(device_registry, "_WARNED_UNSUPPORTED_DEVCODES", set())


def test_unsupported_devcode_warning_explains_limitations_and_support(
    caplog: pytest.LogCaptureFixture,
) -> None:
    point = {"title": "Battery Voltage", "val": "53.2", "unit": "V"}

    with caplog.at_level(logging.WARNING):
        result = apply_devcode_transformations(9998, point)

    assert result == {"title": "Battery Voltage", "val": "53.2", "unit": "V"}
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "Unsupported devcode 9998" in message
    assert "device-specific mappings" in message
    assert "raw sensor titles and values" in message
    assert "limited" in message
    assert "request or add support" in message
    assert (
        "https://github.com/andreas-glaser/ha-dessmonitor/blob/dev/"
        "docs/ADDING_DEVCODES.md#request-support"
    ) in message


def test_unsupported_warning_is_once_per_devcode(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        for devcode in (9998, 9999, 9998, 9999):
            for title in ("Battery Voltage", "Output Voltage"):
                point = {"title": title, "val": "53.2"}
                assert apply_devcode_transformations(devcode, point) == point

    assert len(caplog.records) == 2
    assert "Unsupported devcode 9998" in caplog.records[0].getMessage()
    assert "Unsupported devcode 9999" in caplog.records[1].getMessage()


def test_supported_devcode_still_transforms_without_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    point = {"title": "Battery percentage", "val": "85", "unit": "%"}

    with caplog.at_level(logging.WARNING):
        result = apply_devcode_transformations(2376, point)

    assert result == {"title": "State of Charge", "val": "85", "unit": "%"}
    assert point == {"title": "Battery percentage", "val": "85", "unit": "%"}
    assert not caplog.records


async def test_2376_title_cleanup_preserves_sensor_identities_and_values() -> None:
    """Current telemetry and legacy energy aliases keep their published entities."""
    readings = [
        ("INV Module Termperature", "41", "inv_module_termperature"),
        ("DC Module Termperature", "42", "dc_module_termperature"),
        ("Output frequency", "60.15", "output_frequency"),
        ("energyToday", "12.5", "energytoday"),
        ("energyTotal", "1234.5", "energytotal"),
        ("outpower", "441", "pv_power"),
        ("PV Charge Power", "440", "pv_charge_power"),
        ("AC charging power", "0", "ac_charging_power"),
        ("Battery Power", "12", "battery_power"),
        ("Battery percentage", "100", "state_of_charge"),
    ]
    coordinator = MagicMock()
    coordinator.data = {
        "TEST-INVERTER": {
            "device": {"devcode": 2376},
            "collector": {"pn": "TEST-COLLECTOR"},
            "data": [{"title": title, "val": value} for title, value, _ in readings],
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()
    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
    assert {
        entity.unique_id: entity.native_value for entity in added.call_args.args[0]
    } == {f"TEST-INVERTER_{suffix}": float(value) for _, value, suffix in readings}
