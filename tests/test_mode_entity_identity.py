"""Real HA reloads must preserve registry IDs and automation references."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
from custom_components.dessmonitor.const import (
    CONF_LOCAL_MODE,
    DOMAIN,
    LOCAL_MODE_DISABLED,
    LOCAL_MODE_PREFER_LOCAL,
)
from custom_components.dessmonitor.local.hybrid import merge_cloud_and_local


async def test_options_reload_preserves_entity_ids_and_automation(hass):
    """Use real platform unload/setup and registry, with transport/startup stubbed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "test", "password": "test"},
        options={CONF_LOCAL_MODE: LOCAL_MODE_DISABLED},
    )
    entry.add_to_hass(hass)
    api = AsyncMock()

    async def read_control_value(_pn, _devcode, _devaddr, _sn, field_id):
        return {"val": {"priority": "1", "current": "10"}[field_id]}

    api.get_device_control_value.side_effect = read_control_value
    api.get_device_control_fields.return_value = {
        "Main Output Priority": {
            "type": "options",
            "id": "priority",
            "options": {"1": "SUB", "2": "SBU"},
        },
        "Maximum mains charging current": {
            "type": "value",
            "id": "current",
            "unit": "A",
        },
    }
    cloud = {
        "CLOUD-SERIAL": {
            "device": {"devcode": 6544, "devaddr": 1, "alias": "Test inverter"},
            "collector": {"pn": "COLLECTOR"},
            "data": [
                {"title": "Battery Voltage", "val": "53.9", "unit": "V"},
                {"title": "Main Output Priority", "val": "SUB", "unit": ""},
                {"title": "Maximum mains charging current", "val": "10", "unit": "A"},
            ],
        }
    }
    local = {
        "LOCAL-SERIAL": {
            "device": {"devaddr": 1, "local_address_verified": True},
            "collector": {"pn": "COLLECTOR"},
            "data": [
                {"title": "Battery Voltage", "val": 54.0, "unit": "V"},
                {"title": "Inverter Current", "val": 3.0, "unit": "A"},
            ],
        }
    }

    async def make_coordinator(hass, current_entry, _api):
        coordinator = DessMonitorDataUpdateCoordinator(
            hass, api, 300, config_entry=current_entry
        )
        coordinator._cached_cloud_data = deepcopy(cloud)
        coordinator.cloud_revision = 1
        hybrid = current_entry.options[CONF_LOCAL_MODE] == LOCAL_MODE_PREFER_LOCAL
        coordinator.async_set_updated_data(
            merge_cloud_and_local(cloud, local, local_available=hybrid)
        )
        return coordinator

    calls = []

    @callback
    def record(call):
        calls.append(call)

    hass.services.async_register("identity_test", "record", record)
    with (
        patch("custom_components.dessmonitor._create_api_client", return_value=api),
        patch(
            "custom_components.dessmonitor._authenticate_api_client", new=AsyncMock()
        ),
        patch(
            "custom_components.dessmonitor._create_coordinator",
            side_effect=make_coordinator,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        sensor_id = registry.async_get_entity_id(
            "sensor", DOMAIN, "CLOUD-SERIAL_battery_voltage"
        )
        assert sensor_id
        voltage = registry.async_update_entity(
            sensor_id, new_entity_id="sensor.my_battery_voltage"
        )
        await hass.async_block_till_done()
        select_id = registry.async_get_entity_id(
            "select", DOMAIN, "CLOUD-SERIAL_main_output_priority"
        )
        number_id = registry.async_get_entity_id(
            "number", DOMAIN, "CLOUD-SERIAL_maximum_mains_charging_current"
        )
        assert select_id and number_id
        initial = {
            item.unique_id: (item.entity_id, item.id, item.device_id)
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": [
                    {
                        "alias": "Existing DessMonitor reference",
                        "trigger": {
                            "platform": "state",
                            "entity_id": voltage.entity_id,
                            "to": "55.0",
                        },
                        "action": {"service": "identity_test.record"},
                    }
                ]
            },
        )
        await hass.async_block_till_done()
        local_entry = None
        try:
            for mode in (
                LOCAL_MODE_PREFER_LOCAL,
                LOCAL_MODE_DISABLED,
                LOCAL_MODE_PREFER_LOCAL,
            ):
                hass.config_entries.async_update_entry(
                    entry, options={CONF_LOCAL_MODE: mode}
                )
                await hass.async_block_till_done()
                current = {
                    item.unique_id: (item.entity_id, item.id, item.device_id)
                    for item in er.async_entries_for_config_entry(
                        registry, entry.entry_id
                    )
                }
                assert all(
                    current[key] == identity for key, identity in initial.items()
                )
                assert hass.states.get(voltage.entity_id).state in {"53.9", "54.0"}
                assert hass.states.get(select_id).state == "SUB"
                assert hass.states.get(number_id).state == "10.0"
                local_id = registry.async_get_entity_id(
                    "sensor", DOMAIN, "CLOUD-SERIAL_inverter_current"
                )
                assert local_id
                if local_entry is None:
                    local_entry = registry.async_get(local_id)
                assert registry.async_get(local_id).id == local_entry.id
                if mode == LOCAL_MODE_DISABLED:
                    state = hass.states.get(local_id)
                    assert state is None or state.state == "unavailable"
                else:
                    assert hass.states.get(local_id).state == "3.0"

            coordinator = hass.data[DOMAIN][entry.entry_id]
            data = deepcopy(coordinator.data)
            next(
                point
                for point in data["CLOUD-SERIAL"]["data"]
                if point["title"] == "Battery Voltage"
            )["val"] = 55.0
            coordinator.async_set_updated_data(data)
            await hass.async_block_till_done()
            assert len(calls) == 1
        finally:
            await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
