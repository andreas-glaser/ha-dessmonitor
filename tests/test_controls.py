"""Cloud-control regressions shared by API and hybrid modes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.dessmonitor.button import (
    DessMonitorButton,
    _async_build_button_entities,
)
from custom_components.dessmonitor.select import (
    DessMonitorSelect,
    _async_build_select_entities,
)


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
    return coordinator


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


async def test_select_write_remains_cloud_backed_in_hybrid() -> None:
    """Changing a hybrid control uses only the authenticated cloud API."""
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
    assert coordinator.ctrl_value_cache["DEVICE-SERIAL"]["mode"] == "Utility"
    write_state.assert_called_once_with()


async def test_action_button_remains_cloud_backed_in_hybrid() -> None:
    """A one-shot action never gains a local write path."""
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
