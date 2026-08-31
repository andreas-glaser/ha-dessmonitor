"""Regression tests for enum sensor contracts."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor.button import _disable_replaced_selects
from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.sensor import DessMonitorSensor


def _enum_sensor(title: str, value: str) -> DessMonitorSensor:
    """Create an enum sensor with the minimum coordinator surface."""
    serial = "TEST-SERIAL"
    data_point = {"title": title, "val": value}
    payload = {
        "device": {"alias": "Test inverter", "devcode": 2376},
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


@pytest.mark.parametrize(
    ("title", "live_value"),
    [
        ("Output priority", "Utility First"),
        ("Charger Source Priority", "PV is at the same level as mains"),
    ],
)
def test_enum_contract_accepts_live_cloud_values(
    title: str, live_value: str
) -> None:
    """Known and firmware-specific live states must satisfy HA's enum contract."""
    entity = _enum_sensor(title, live_value)

    assert entity.native_value == live_value
    assert live_value in entity.options
    assert "Unknown" in entity.options


async def test_replaced_one_option_select_is_disabled_not_deleted(
    hass: HomeAssistant,
) -> None:
    """The action button hides its obsolete select while preserving registry data."""
    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    unique_id = "TEST-SERIAL_reset_user_settings"
    legacy = registry.async_get_or_create(
        "select", DOMAIN, unique_id, config_entry=config_entry
    )
    button = MagicMock()
    button.unique_id = unique_id

    _disable_replaced_selects(hass, config_entry, [button])

    preserved = registry.async_get(legacy.entity_id)
    assert preserved is not None
    assert preserved.disabled_by is er.RegistryEntryDisabler.INTEGRATION
