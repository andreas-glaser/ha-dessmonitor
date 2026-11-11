"""Regression tests for enum sensor contracts."""

from __future__ import annotations

from typing import Any
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
    payload: dict[str, Any] = {
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
    ("title", "live_value", "expected"),
    [
        ("Output priority", "Utility First", "Utility First"),
        (
            "Charger Source Priority",
            "PV is at the same level as mains",
            "Solar and grid equal",
        ),
        (
            "Charger Source Priority",
            "PV Is At The Same Level As Utility",
            "Solar and grid equal",
        ),
        (
            "Charger Source Priority",
            "Undocumented firmware priority",
            "Undocumented firmware priority",
        ),
    ],
)
def test_enum_contract_accepts_live_cloud_values(
    title: str, live_value: str, expected: str
) -> None:
    """Known and firmware-specific live states must satisfy HA's enum contract."""
    entity = _enum_sensor(title, live_value)

    assert entity.native_value == expected
    options = entity.options
    assert options is not None
    assert expected in options
    assert "Unknown" in options


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
    button.legacy_unique_id = "TEST-SERIAL_reset_user_settings_legacy"

    _disable_replaced_selects(hass, config_entry, [button])

    preserved = registry.async_get(legacy.entity_id)
    assert preserved is not None
    assert preserved.disabled_by is er.RegistryEntryDisabler.INTEGRATION


def test_a_state_first_seen_later_is_added_to_the_options() -> None:
    """An option list fixed at creation took the sensor down on a new value.

    Home Assistant rejects an enum state outside the entity's options. The
    list is built from everything every devcode maps plus the value the
    entity starts with, so a collector that names a state no profile
    registered broke the sensor the first time it reported it. Devcode 6489's
    download observed only "Battery mode", taken while the reporter's mains
    was out, so "Mains mode" is exactly that case (#66).
    """
    entity = _enum_sensor("Operating mode", "Battery mode")
    assert entity.native_value == "Battery mode"

    unregistered = "Battery eco mode"
    assert unregistered not in (
        entity.options or []
    ), "pick a state no devcode maps, or this test proves nothing"
    entity.coordinator.data["TEST-SERIAL"]["data"] = [
        {"title": "Operating mode", "val": unregistered}
    ]

    value = entity.native_value
    options = entity.options
    assert value == unregistered
    assert options is not None and value in options, (
        "Home Assistant raises on a state outside the options, so the entity "
        "would go unavailable instead of showing the state"
    )


def test_an_option_list_cannot_grow_without_end() -> None:
    """A reading misread as an enumeration would otherwise collect every value.

    Past the bound the sensor reads Unknown, which is always an option, and
    says so once per value rather than publishing an invalid state.
    """
    from custom_components.dessmonitor.sensor import _MAX_ENUM_OPTIONS

    entity = _enum_sensor("Operating mode", "Battery mode")
    options = entity.options
    assert options is not None

    for index in range(_MAX_ENUM_OPTIONS + 10):
        entity.coordinator.data["TEST-SERIAL"]["data"] = [
            {"title": "Operating mode", "val": f"mode-{index}"}
        ]
        value = entity.native_value
        assert value in (entity.options or [])

    assert len(entity.options or []) == _MAX_ENUM_OPTIONS
    assert entity.native_value == "Unknown"
