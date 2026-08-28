"""Tests for DessMonitor numeric control entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.number import NumberMode

from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.number import DessMonitorNumber, async_setup_entry


def _make_coordinator(value: str = "9") -> MagicMock:
    """Create the coordinator surface used by a number entity."""
    coordinator = MagicMock()
    coordinator.data = {
        "SN-1": {
            "device": {"alias": "Test inverter", "devcode": 6544, "devaddr": 1},
            "collector": {"pn": "PN-1"},
            "data": [
                {
                    "title": "Maximum mains charging current",
                    "val": value,
                    "unit": "A",
                }
            ],
        }
    }
    coordinator.ctrl_value_cache = {"SN-1": {"bat_current": value}}
    return coordinator


def _make_entity(
    coordinator: MagicMock, initial_value: str = "9", hint: str | None = None
) -> DessMonitorNumber:
    """Create the numeric control reported in issue #30."""
    return DessMonitorNumber(
        coordinator=coordinator,
        device_sn="SN-1",
        device_meta={"alias": "Test inverter", "devcode": 6544, "devaddr": 1},
        collector_meta={"pn": "PN-1"},
        name="Maximum mains charging current",
        api_name="Maximum mains charging current",
        param_id="bat_current",
        initial_value=initial_value,
        unit="A",
        hint=hint,
    )


async def test_setup_adds_only_valid_value_controls() -> None:
    """Platform setup preserves the API name and accepts zero-valued IDs."""
    coordinator = _make_coordinator()
    coordinator.data = {
        "SN-0": {
            "device": {"alias": "Test inverter", "devcode": 0, "devaddr": 0},
            "collector": {"pn": "PN-0"},
            "data": [],
        },
        "SN-MISSING-PN": {
            "device": {"alias": "Skipped", "devcode": 6544, "devaddr": 1},
            "collector": {},
            "data": [],
        },
    }
    coordinator.async_get_controls_with_values = AsyncMock(
        return_value=(
            {
                "Raw current name": {
                    "type": "value",
                    "id": "current_id",
                    "unit": "A",
                    "hint": None,
                },
                "Select control": {
                    "type": "options",
                    "id": "select_id",
                    "options": {"0": "Off"},
                },
                "Missing ID": {"type": "value", "id": "", "unit": "V"},
            },
            {"current_id": "9"},
        )
    )
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry-1": coordinator}}
    config_entry = MagicMock(entry_id="entry-1")
    async_add_entities = MagicMock()

    with patch(
        "custom_components.dessmonitor.number.map_control_field",
        return_value="Mapped current name",
    ) as map_control:
        await async_setup_entry(hass, config_entry, async_add_entities)

    coordinator.async_get_controls_with_values.assert_awaited_once_with(
        "PN-0", 0, 0, "SN-0"
    )
    map_control.assert_called_once_with(0, "Raw current name")
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args.args[0]
    assert len(entities) == 1
    entity = entities[0]
    assert isinstance(entity, DessMonitorNumber)
    assert entity._api_name == "Raw current name"
    assert entity._param_name == "Mapped current name"
    assert entity.native_value == 9.0


async def test_setup_without_coordinator_data_adds_nothing() -> None:
    """An empty first refresh does not create number entities."""
    coordinator = _make_coordinator()
    coordinator.data = {}
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry-1": coordinator}}
    async_add_entities = MagicMock()

    await async_setup_entry(hass, MagicMock(entry_id="entry-1"), async_add_entities)

    async_add_entities.assert_not_called()


async def test_setup_without_value_controls_adds_nothing() -> None:
    """A device exposing only selects does not create a number platform batch."""
    coordinator = _make_coordinator()
    coordinator.async_get_controls_with_values = AsyncMock(
        return_value=(
            {"Mode": {"type": "options", "id": "mode", "options": {"0": "Off"}}},
            {"mode": "0"},
        )
    )
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry-1": coordinator}}
    async_add_entities = MagicMock()

    await async_setup_entry(hass, MagicMock(entry_id="entry-1"), async_add_entities)

    async_add_entities.assert_not_called()


def test_missing_hint_uses_stable_box_range() -> None:
    """A startup value must not become an artificial min/max constraint."""
    entity = _make_entity(_make_coordinator())

    assert entity.native_value == 9.0
    assert entity.native_min_value == 0.0
    assert entity.native_max_value == 200.0
    assert entity.native_step == 0.1
    assert entity.mode is NumberMode.BOX


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("22A", 22.0), (" 57.6 V ", 57.6), ("-1.5", -1.5), (".5A", 0.5)],
)
def test_control_value_parser_accepts_number_with_optional_unit(
    raw: str, expected: float
) -> None:
    assert DessMonitorNumber._coerce_value(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "1~2A", "2026-08-28", "prefix 22A", "1e2", "nan", "inf"]
)
def test_control_value_parser_rejects_ambiguous_input(raw: str) -> None:
    assert DessMonitorNumber._coerce_value(raw) is None


def test_control_value_parser_accepts_none() -> None:
    assert DessMonitorNumber._coerce_value(None) is None


def test_invalid_initial_value_is_left_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed startup data cannot become an invalid Home Assistant state."""
    with caplog.at_level("WARNING"):
        entity = _make_entity(_make_coordinator(), initial_value="not-a-number")

    assert entity.native_value is None
    assert "Could not convert initial value" in caplog.text


def test_missing_initial_value_is_left_unknown_without_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unavailable startup value is normal and still gets a usable range."""
    with caplog.at_level("WARNING"):
        entity = _make_entity(_make_coordinator(), initial_value=None)

    assert entity.native_value is None
    assert entity.native_min_value == 0.0
    assert entity.native_max_value == 200.0
    assert "Could not convert initial value" not in caplog.text


def test_coordinator_update_refreshes_external_control_change() -> None:
    """A value changed in DessMonitor is reflected by normal coordinator polling."""
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)
    coordinator.data["SN-1"]["data"][0]["val"] = "22A"

    with patch.object(entity, "async_write_ha_state") as write_state:
        entity._handle_coordinator_update()

    assert entity.native_value == 22.0
    assert entity.native_min_value == 0.0
    assert entity.native_max_value == 200.0
    assert coordinator.ctrl_value_cache["SN-1"]["bat_current"] == "22.0"
    write_state.assert_called_once_with()


def test_coordinator_update_without_matching_control_preserves_value() -> None:
    """Unrelated polled data cannot overwrite the cached control state."""
    coordinator = _make_coordinator()
    entity = _make_entity(coordinator)
    coordinator.data["SN-1"]["data"] = [
        {"title": None, "val": "22"},
        {"title": "Different control", "val": "22"},
    ]

    with patch.object(entity, "async_write_ha_state") as write_state:
        entity._handle_coordinator_update()

    assert entity.native_value == 9.0
    assert coordinator.ctrl_value_cache["SN-1"]["bat_current"] == "9"
    write_state.assert_called_once_with()


def test_external_value_outside_hint_expands_range_and_uses_box() -> None:
    """A newly contradicted hint cannot leave the refreshed state out of range."""
    coordinator = _make_coordinator("20")
    entity = _make_entity(coordinator, initial_value="20", hint="5~80A")
    assert entity.native_min_value == 5.0
    assert entity.native_max_value == 80.0
    assert entity.mode is NumberMode.AUTO

    coordinator.data["SN-1"]["data"][0]["val"] = "120"
    with patch.object(entity, "async_write_ha_state"):
        entity._handle_coordinator_update()

    assert entity.native_value == 120.0
    assert entity.native_min_value == 0.0
    assert entity.native_max_value == 200.0
    assert entity.mode is NumberMode.BOX


def test_external_value_inside_hint_keeps_slider_range() -> None:
    """A trustworthy range remains a slider while its value is refreshed."""
    coordinator = _make_coordinator("20")
    entity = _make_entity(coordinator, initial_value="20", hint="5~80A")
    coordinator.data["SN-1"]["data"][0]["val"] = "22"

    with patch.object(entity, "async_write_ha_state"):
        entity._handle_coordinator_update()

    assert entity.native_value == 22.0
    assert entity.native_min_value == 5.0
    assert entity.native_max_value == 80.0
    assert entity.mode is NumberMode.AUTO


def test_external_value_refreshes_without_control_cache() -> None:
    """A missing optional cache entry does not prevent coordinator refreshes."""
    coordinator = _make_coordinator()
    coordinator.ctrl_value_cache = {}
    entity = _make_entity(coordinator)
    coordinator.data["SN-1"]["data"][0]["val"] = "22"

    with patch.object(entity, "async_write_ha_state"):
        entity._handle_coordinator_update()

    assert entity.native_value == 22.0
    assert coordinator.ctrl_value_cache == {}


async def test_successful_write_updates_state_and_cache() -> None:
    """State is updated only after DessMonitor accepts the requested value."""
    coordinator = _make_coordinator()
    coordinator.api.set_device_control_value = AsyncMock(return_value={"err": 0})
    entity = _make_entity(coordinator)

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_set_native_value(25.0)

    coordinator.api.set_device_control_value.assert_awaited_once_with(
        pn="PN-1",
        devcode=6544,
        devaddr=1,
        sn="SN-1",
        param_id="bat_current",
        value="25.0",
    )
    assert entity.native_value == 25.0
    assert coordinator.ctrl_value_cache["SN-1"]["bat_current"] == "25.0"
    write_state.assert_called_once_with()


async def test_successful_write_without_control_cache_updates_state() -> None:
    """Successful writes do not depend on the optional startup cache."""
    coordinator = _make_coordinator()
    coordinator.ctrl_value_cache = {}
    coordinator.api.set_device_control_value = AsyncMock(return_value={"err": 0})
    entity = _make_entity(coordinator)

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_set_native_value(25.0)

    assert entity.native_value == 25.0
    assert coordinator.ctrl_value_cache == {}
    write_state.assert_called_once_with()


async def test_failed_write_preserves_state_and_cache() -> None:
    """An API rejection must not be represented as a successful local change."""
    coordinator = _make_coordinator()
    coordinator.api.set_device_control_value = AsyncMock(
        side_effect=RuntimeError("device rejected value")
    )
    entity = _make_entity(coordinator)

    with (
        patch.object(entity, "async_write_ha_state") as write_state,
        pytest.raises(RuntimeError, match="device rejected value"),
    ):
        await entity.async_set_native_value(25.0)

    assert entity.native_value == 9.0
    assert coordinator.ctrl_value_cache["SN-1"]["bat_current"] == "9"
    write_state.assert_not_called()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_write_is_rejected_locally(value: float) -> None:
    """Never serialize non-finite values into a device control request."""
    coordinator = _make_coordinator()
    coordinator.api.set_device_control_value = AsyncMock()
    entity = _make_entity(coordinator)

    with pytest.raises(ValueError, match="finite number"):
        await entity.async_set_native_value(value)

    coordinator.api.set_device_control_value.assert_not_awaited()
    assert entity.native_value == 9.0
    assert coordinator.ctrl_value_cache["SN-1"]["bat_current"] == "9"
