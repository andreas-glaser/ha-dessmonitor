"""Control recovery uses cloud revisions, not fast local telemetry updates."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.dessmonitor import (
    MAX_CONTROL_VALUE_RETRIES,
    DessMonitorDataUpdateCoordinator,
)
from custom_components.dessmonitor.api import DessMonitorError
from custom_components.dessmonitor.control_values import control_value
from custom_components.dessmonitor.number import _async_build_number_entities
from custom_components.dessmonitor.select import _async_build_select_entities

CONTROLS = {
    "Main Output Priority": {
        "type": "options",
        "id": "priority",
        "options": {"1": "SUB", "2": "SBU"},
    },
    "Maximum mains charging current": {"type": "value", "id": "current", "unit": "A"},
    "Reset": {"type": "options", "id": "reset", "options": {"1": "Reset"}},
}


def _cloud(stamp="first", *points):
    return {
        "TEST": {
            "collector": {"pn": "PN"},
            "device": {"devcode": 6544, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": "Timestamp", "val": stamp}, *points],
        }
    }


def _point(title, value):
    return {"title": title, "val": value, "unit": ""}


def _coordinator(hass, data):
    api = AsyncMock()
    api.get_device_control_fields.return_value = CONTROLS
    api.get_device_control_value.side_effect = DessMonitorError("ERR_TIMEOUT", 2)
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    coordinator.cloud_revision = 1
    coordinator._cached_cloud_data = data
    coordinator.async_set_updated_data(data)
    return coordinator


async def _publish_cloud(coordinator, data):
    # Exercise the production cloud refresh path, including cache synchronization.
    with (
        patch.object(coordinator, "_fetch_collectors", AsyncMock(return_value=[])),
        patch.object(
            coordinator, "_gather_all_device_data", AsyncMock(return_value=data)
        ),
        patch.object(coordinator, "_merge_summary_data", AsyncMock()),
    ):
        result = await coordinator._async_update_data()
    coordinator.async_set_updated_data(result)


async def test_cloud_payload_seeds_controls_and_skips_action_reads(hass):
    coordinator = _coordinator(
        hass,
        _cloud(
            "first",
            _point("Main Output Priority", "SUB"),
            _point("Maximum mains charging current", "0A"),
        ),
    )
    (select,) = await _async_build_select_entities(coordinator, set())
    (number,) = await _async_build_number_entities(coordinator, set())
    assert select.current_option == "SUB" and select.available
    assert number.native_value == 0 and number.available
    coordinator.api.get_device_control_fields.assert_awaited_once()
    coordinator.api.get_device_control_value.assert_not_awaited()
    assert select.extra_state_attributes["control_transport"] == "cloud"
    await coordinator.async_shutdown()


async def test_failed_values_recover_existing_entities_without_reload(hass):
    coordinator = _coordinator(hass, _cloud())
    select_known, number_known = set(), set()
    (select,) = await _async_build_select_entities(coordinator, select_known)
    (number,) = await _async_build_number_entities(coordinator, number_known)
    assert select.current_option is None and number.native_value is None
    assert select.extra_state_attributes["value_status"] == "not_loaded"
    assert number.extra_state_attributes["value_status"] == "not_loaded"
    assert coordinator.api.get_device_control_value.await_count == 2

    # Simulate many local pushes / three platforms. No retry in the same revision.
    for _ in range(10):
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert coordinator.api.get_device_control_value.await_count == 2

    async def read(_pn, _devcode, _address, _sn, field):
        return {"val": "2" if field == "priority" else "17A"}

    coordinator.api.get_device_control_value.side_effect = read
    # A successful cloud update permits one retry, even when its telemetry
    # still lacks these two settings.
    await _publish_cloud(coordinator, _cloud("second"))
    with patch.object(select, "async_write_ha_state"), patch.object(
        number, "async_write_ha_state"
    ):
        remove_select = coordinator.async_add_listener(
            select._handle_coordinator_update
        )
        remove_number = coordinator.async_add_listener(
            number._handle_coordinator_update
        )
        try:
            assert await _async_build_select_entities(coordinator, select_known) == []
            assert await _async_build_number_entities(coordinator, number_known) == []
            assert select.current_option == "SBU" and select.available
            assert number.native_value == 17 and number.available
        finally:
            remove_select()
            remove_number()
    assert coordinator.api.get_device_control_value.await_count == 4
    await coordinator.async_shutdown()


async def test_external_changes_refresh_controls_without_per_field_requests(hass):
    coordinator = _coordinator(
        hass,
        _cloud(
            "first",
            _point("Main Output Priority", "SUB"),
            _point("Current output priority", "SBU"),
            _point("Maximum mains charging current", "10A"),
        ),
    )
    (select,) = await _async_build_select_entities(coordinator, set())
    (number,) = await _async_build_number_entities(coordinator, set())
    with patch.object(select, "async_write_ha_state"), patch.object(
        number, "async_write_ha_state"
    ):
        remove_select = coordinator.async_add_listener(
            select._handle_coordinator_update
        )
        remove_number = coordinator.async_add_listener(
            number._handle_coordinator_update
        )
        try:
            await _publish_cloud(
                coordinator,
                _cloud(
                    "second",
                    _point("Main Output Priority", "SBU"),
                    _point("Current output priority", "SUB"),
                    _point("Maximum mains charging current", "20A"),
                ),
            )
            assert select.current_option == "SBU"
            assert number.native_value == 20
            # Placeholder values do not destroy last-known settings.
            await _publish_cloud(
                coordinator,
                _cloud(
                    "third",
                    _point("Main Output Priority", "null"),
                    _point("Maximum mains charging current", "-"),
                ),
            )
            assert select.current_option == "SBU" and number.native_value == 20
        finally:
            remove_select()
            remove_number()
    coordinator.api.get_device_control_value.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_local_push_and_repeated_cloud_sample_do_not_undo_accepted_write(hass):
    data = _cloud(
        "first",
        _point("Main Output Priority", "SUB"),
        _point("Maximum mains charging current", "10A"),
    )
    coordinator = _coordinator(hass, data)
    (select,) = await _async_build_select_entities(coordinator, set())
    (number,) = await _async_build_number_entities(coordinator, set())
    with patch.object(select, "async_write_ha_state"), patch.object(
        number, "async_write_ha_state"
    ):
        await select.async_select_option("SBU")
        await number.async_set_native_value(25)
        for _ in range(10):
            coordinator.data = _cloud("local-generated-time")
            select._handle_coordinator_update()
            number._handle_coordinator_update()
        await _publish_cloud(
            coordinator, data
        )  # API returns the same upstream Timestamp.
        select._handle_coordinator_update()
        number._handle_coordinator_update()
        assert select.current_option == "SBU" and number.native_value == 25
        # A genuinely new cloud sample can report a later external change.
        await _publish_cloud(
            coordinator,
            _cloud(
                "second",
                _point("Main Output Priority", "SUB"),
                _point("Maximum mains charging current", "30A"),
            ),
        )
        select._handle_coordinator_update()
        number._handle_coordinator_update()
        assert select.current_option == "SUB" and number.native_value == 30
    await coordinator.async_shutdown()


async def test_failed_definitions_retry_once_per_cloud_revision(hass):
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_fields.side_effect = DessMonitorError("offline")
    for _ in range(3):
        assert await coordinator.async_get_controls_with_values(
            "PN", 6544, 1, "TEST"
        ) == ({}, {})
    coordinator.api.get_device_control_fields.assert_awaited_once()
    coordinator.cloud_revision += 1
    coordinator.api.get_device_control_fields.side_effect = None
    controls, _ = await coordinator.async_get_controls_with_values(
        "PN", 6544, 1, "TEST"
    )
    assert controls == CONTROLS
    assert coordinator.api.get_device_control_fields.await_count == 2
    await coordinator.async_shutdown()


async def test_inflight_read_does_not_overwrite_more_recent_cache_value(hass):
    coordinator = _coordinator(hass, _cloud())
    started, release = asyncio.Event(), asyncio.Event()

    async def read(*args):
        started.set()
        await release.wait()
        return {"val": "1"}

    coordinator.api.get_device_control_value.side_effect = read
    task = asyncio.create_task(
        coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    )
    await started.wait()
    coordinator.ctrl_value_cache["TEST"]["priority"] = "SBU"
    release.set()
    _, values = await task
    assert values["priority"] == "SBU"
    await coordinator.async_shutdown()


async def test_cloud_outage_keeps_last_known_controls(hass):
    coordinator = _coordinator(
        hass,
        _cloud(
            "first",
            _point("Main Output Priority", "SUB"),
            _point("Maximum mains charging current", "10A"),
        ),
    )
    (select,) = await _async_build_select_entities(coordinator, set())
    (number,) = await _async_build_number_entities(coordinator, set())
    with patch.object(
        coordinator,
        "_fetch_collectors",
        AsyncMock(side_effect=DessMonitorError("offline")),
    ):
        cached = await coordinator._async_update_data()
    coordinator.async_set_updated_data(cached)
    with patch.object(select, "async_write_ha_state"), patch.object(
        number, "async_write_ha_state"
    ):
        select._handle_coordinator_update()
        number._handle_coordinator_update()
    assert select.current_option == "SUB"
    assert number.native_value == 10
    assert select.extra_state_attributes["value_status"] == "last_known"
    assert coordinator.cloud_revision == 1
    await coordinator.async_shutdown()


async def test_unsupported_select_value_is_retried_after_recovery(hass):
    coordinator = _coordinator(
        hass, _cloud("first", _point("Main Output Priority", "bad"))
    )
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "null"}
    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert values == {}
    coordinator.cloud_revision += 1
    coordinator.api.get_device_control_value.return_value = {"val": "2"}
    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert values["priority"] == "2"
    await coordinator.async_shutdown()


async def test_time_string_is_identified_as_unsupported_number_format(hass):
    coordinator = _coordinator(
        hass, _cloud("first", _point("Secondary Output Priority Start Time", "15:30"))
    )
    coordinator.api.get_device_control_fields.return_value = {
        "Secondary Output Priority Start Time": {"type": "value", "id": "time"}
    }
    (number,) = await _async_build_number_entities(coordinator, set())
    assert number.native_value is None
    assert number.extra_state_attributes["value_status"] == "unsupported_format"
    coordinator.api.get_device_control_value.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_permanently_unreadable_values_stop_being_re_read(hass):
    """An unresolvable field must not cost one request every cloud refresh."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "null"}
    for _ in range(MAX_CONTROL_VALUE_RETRIES + 3):
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
        coordinator.cloud_revision += 1
    # Two readable fields per round; "Reset" is a single-option action.
    assert (
        coordinator.api.get_device_control_value.await_count
        == 2 * MAX_CONTROL_VALUE_RETRIES
    )
    await coordinator.async_shutdown()


async def test_partial_recovery_restores_the_retry_budget(hass):
    """A device still making progress keeps retrying whatever is left."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "null"}
    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    coordinator.cloud_revision += 1

    # One field recovers, which must not be counted as a wasted round.
    coordinator.api.get_device_control_value.side_effect = [
        {"val": "2"},
        {"val": "null"},
    ]
    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert values["priority"] == "2"
    assert coordinator._ctrl_value_retries["TEST"] == 0

    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "null"}
    before = coordinator.api.get_device_control_value.await_count
    for _ in range(MAX_CONTROL_VALUE_RETRIES + 2):
        coordinator.cloud_revision += 1
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    # Only the remaining field is still missing, for a bounded run of rounds.
    assert (
        coordinator.api.get_device_control_value.await_count - before
        == MAX_CONTROL_VALUE_RETRIES
    )
    await coordinator.async_shutdown()


async def test_ordinary_telemetry_recovers_existing_entities_after_budget_exhausted(hass):
    """Stopping per-field reads must not strand entities at unknown."""
    coordinator = _coordinator(hass, _cloud())
    select_known, number_known = set(), set()
    (select,) = await _async_build_select_entities(coordinator, select_known)
    (number,) = await _async_build_number_entities(coordinator, number_known)
    try:
        for index in range(MAX_CONTROL_VALUE_RETRIES + 1):
            await _publish_cloud(coordinator, _cloud(f"missing-{index}"))
            await _async_build_select_entities(coordinator, select_known)
            await _async_build_number_entities(coordinator, number_known)
        reads = coordinator.api.get_device_control_value.await_count
        assert reads == 2 * MAX_CONTROL_VALUE_RETRIES
        assert select.current_option is None and number.native_value is None
        with patch.object(select, "async_write_ha_state"), patch.object(
            number, "async_write_ha_state"
        ):
            remove_select = coordinator.async_add_listener(
                select._handle_coordinator_update
            )
            remove_number = coordinator.async_add_listener(
                number._handle_coordinator_update
            )
            try:
                await _publish_cloud(
                    coordinator,
                    _cloud(
                        "recovered",
                        _point("Main Output Priority", "SBU"),
                        _point("Maximum mains charging current", "17A"),
                    ),
                )
                assert select.current_option == "SBU"
                assert number.native_value == 17
                assert await _async_build_select_entities(coordinator, select_known) == []
                assert await _async_build_number_entities(coordinator, number_known) == []
                assert coordinator.api.get_device_control_value.await_count == reads
                coordinator.api.set_device_control_value.assert_not_awaited()
            finally:
                remove_select()
                remove_number()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "value", [None, "null", "NULL", "", "unknown", "unavailable", "nan", {}, []]
)
def test_placeholder_values_are_not_valid_cache_entries(value):
    assert control_value(value) is None
