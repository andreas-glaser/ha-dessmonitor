"""Cloud-control regressions shared by API and hybrid modes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor.button import (
    DessMonitorButton,
    _async_build_button_entities,
)
from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.number import _async_build_number_entities
from custom_components.dessmonitor.select import (
    DessMonitorSelect,
    _async_build_select_entities,
)
from custom_components.dessmonitor.utils import async_migrate_control_unique_ids

from .support import bind_cloud_control_writes


def _coordinator() -> MagicMock:
    """Create one canonical cloud device with mixed control definitions."""
    coordinator = MagicMock()
    coordinator.data = {
        "DEVICE-SERIAL": {
            "collector": {"pn": "COLLECTOR-PN"},
            "device": {"alias": "Test inverter", "devcode": 2376, "devaddr": 1},
            "data": [],
        }
    }
    coordinator.ctrl_value_cache = {
        "DEVICE-SERIAL": {"mode": "1", "reset": "1"}
    }
    coordinator.async_get_controls_with_values = AsyncMock(
        return_value=(
            {
                "Output mode": {
                    "type": "options",
                    "id": "mode",
                    "options": {"0": "Utility", "1": "Solar"},
                },
                "Reset User Settings": {
                    "type": "options",
                    "id": "reset",
                    "options": {"1": "Reset"},
                },
                "Charge current": {
                    "type": "value",
                    "id": "charge_current",
                },
            },
            {"mode": "1", "reset": "1"},
        )
    )
    coordinator.api.set_device_control_value = AsyncMock(return_value={"err": 0})
    return bind_cloud_control_writes(coordinator)


async def test_control_shapes_create_one_select_and_one_button() -> None:
    """Multi-choice fields stay selects and one-shot options become buttons."""
    coordinator = _coordinator()

    selects = await _async_build_select_entities(coordinator, set())
    buttons = await _async_build_button_entities(coordinator, set())

    assert len(selects) == 1
    assert isinstance(selects[0], DessMonitorSelect)
    assert selects[0].current_option == "Solar"
    assert selects[0].options == ["Utility", "Solar"]
    assert len(buttons) == 1
    assert isinstance(buttons[0], DessMonitorButton)
    assert buttons[0].unique_id == "DEVICE-SERIAL_reset_user_settings"


async def test_select_write_takes_the_cloud_when_nothing_pairs_with_it() -> None:
    """An unpaired control writes through the cloud, as it always has.

    A cloud control and a local setting are the same register under two names,
    and this one pairs with nothing: no devcode profile declares it and no
    local setting is named "Output mode". The write therefore takes the cloud
    path, which is what every installation did before local control existed.
    """
    coordinator = _coordinator()
    entity = (await _async_build_select_entities(coordinator, set()))[0]

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_select_option("Utility")

    coordinator.api.set_device_control_value.assert_awaited_once_with(
        pn="COLLECTOR-PN",
        devcode=2376,
        devaddr=1,
        sn="DEVICE-SERIAL",
        param_id="mode",
        value="0",
    )
    assert entity.current_option == "Utility"
    # The cached value is the option's own key, which is the spelling a write
    # has to send and the spelling the platform reports it in.
    assert coordinator.ctrl_value_cache["DEVICE-SERIAL"]["mode"] == "0"
    write_state.assert_called_once_with()


async def test_action_button_writes_through_the_cloud_seam() -> None:
    """A one-shot action takes the same single write seam as every control."""
    coordinator = _coordinator()
    entity = (await _async_build_button_entities(coordinator, set()))[0]

    await entity.async_press()

    coordinator.api.set_device_control_value.assert_awaited_once_with(
        pn="COLLECTOR-PN",
        devcode=2376,
        devaddr=1,
        sn="DEVICE-SERIAL",
        param_id="reset",
        value="1",
    )


def _devcode_6515_coordinator() -> MagicMock:
    """Create a devcode 6515 device with the two control names it reports oddly."""
    coordinator = MagicMock()
    coordinator.data = {
        "DEVICE-SERIAL": {
            "collector": {"pn": "COLLECTOR-PN"},
            "device": {"alias": "Test inverter", "devcode": 6515, "devaddr": 1},
            "data": [],
        }
    }
    coordinator.ctrl_value_cache = {"DEVICE-SERIAL": {}}
    coordinator.async_get_controls_with_values = AsyncMock(
        return_value=(
            {
                " Inverter Time": {
                    "type": "value",
                    "id": "sys_eybond_read_95",
                },
                "bat_eq_time": {
                    "type": "value",
                    "id": "bat_eybond_read_78",
                },
            },
            {},
        )
    )
    return coordinator


async def test_padded_control_name_does_not_reach_a_number_entity() -> None:
    """Devcode 6515 reports " Inverter Time" as a clock, not a number.

    Its confirmed `YYYY-MM-DD HH:MM:SS` read format classifies it as a
    temporal control (see test_temporal_controls.py), which excludes it from
    the number platform the same way the schedule boundaries are excluded.
    The trimming of its leading space is covered directly on
    `map_control_field` in test_devcode_6515.py.
    """
    entities = await _async_build_number_entities(_devcode_6515_coordinator(), set())

    assert all(not e.unique_id.endswith("inverter_time") for e in entities)


async def test_devcode_mapping_names_an_internal_control_identifier() -> None:
    """The collector reports its equalization charge time as "bat_eq_time"."""
    entities = await _async_build_number_entities(_devcode_6515_coordinator(), set())
    entity = next(e for e in entities if e.unique_id.endswith("eq_charging_time"))

    assert entity.name == "Test inverter Eq charging time"
    assert entity.unique_id == "DEVICE-SERIAL_eq_charging_time"
    assert entity.legacy_unique_id == "DEVICE-SERIAL_bat_eq_time"


async def test_renamed_control_keeps_its_registry_entry(hass: HomeAssistant) -> None:
    """Renaming a control carries its entity over instead of duplicating it."""
    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "number", DOMAIN, "DEVICE-SERIAL_bat_eq_time", config_entry=config_entry
    )

    entities = await _async_build_number_entities(_devcode_6515_coordinator(), set())
    async_migrate_control_unique_ids(hass, config_entry, "number", entities)

    entry = registry.async_get(existing.entity_id)
    assert entry is not None
    assert entry.unique_id == "DEVICE-SERIAL_eq_charging_time"
    assert (
        registry.async_get_entity_id("number", DOMAIN, "DEVICE-SERIAL_bat_eq_time")
        is None
    )


async def test_migration_leaves_an_occupied_unique_id_alone(
    hass: HomeAssistant,
) -> None:
    """An entity already registered under the new name is never overwritten."""
    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    legacy = registry.async_get_or_create(
        "number", DOMAIN, "DEVICE-SERIAL_bat_eq_time", config_entry=config_entry
    )
    current = registry.async_get_or_create(
        "number", DOMAIN, "DEVICE-SERIAL_eq_charging_time", config_entry=config_entry
    )

    entities = await _async_build_number_entities(_devcode_6515_coordinator(), set())
    async_migrate_control_unique_ids(hass, config_entry, "number", entities)

    assert registry.async_get(legacy.entity_id).unique_id == "DEVICE-SERIAL_bat_eq_time"
    assert (
        registry.async_get(current.entity_id).unique_id
        == "DEVICE-SERIAL_eq_charging_time"
    )
