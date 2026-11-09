"""Control recovery uses cloud revisions, not fast local telemetry updates."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components import dessmonitor
from custom_components.dessmonitor import (
    CONTROL_VALUE_REFRESH_BASE_INTERVAL_SECONDS,
    CONTROL_VALUE_REFRESH_FAST_INTERVAL_SECONDS,
    CONTROL_VALUE_REFRESH_MAX_INTERVAL_SECONDS,
    CONTROL_VALUE_REFRESH_PER_ROUND,
    MAX_CONTROL_FIELD_RETRIES,
    MAX_CONTROL_VALUE_RETRIES,
    MAX_UNANSWERED_CONTROL_VALUE_RETRIES,
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


def _age_field(coordinator, serial, field_id):
    """Make a field look overdue, whatever the host's uptime.

    The monotonic clock counts from boot, so 0.0 is "half an hour ago" only
    on a machine that has been up for half an hour: these tests passed on a
    developer box and failed on a freshly booted CI runner.
    """
    coordinator._ctrl_value_read_at[(serial, field_id)] = (
        dessmonitor.monotonic() - CONTROL_VALUE_REFRESH_BASE_INTERVAL_SECONDS - 1
    )


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


async def test_a_time_string_control_is_not_published_as_a_number(hass):
    """A clock value is a setting, but not one a number entity can carry.

    With no API hint it would be published with Home Assistant's default
    0-100 range, and a write would send "50" into a schedule field. Devcodes
    whose temporal fields are classified route them to the time and text
    platforms; this is the guard for the rest.
    """
    coordinator = _coordinator(
        hass, _cloud("first", _point("Secondary Output Priority Start Time", "15:30"))
    )
    coordinator.api.get_device_control_fields.return_value = {
        "Secondary Output Priority Start Time": {"type": "value", "id": "time"}
    }
    assert await _async_build_number_entities(coordinator, set()) == []
    coordinator.api.get_device_control_value.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_a_late_time_string_is_reported_and_refuses_a_write(hass):
    """The value can also arrive after the entity exists.

    Nothing can withdraw an entity Home Assistant already has, so the write
    has to be refused instead. The API accepts a malformed setting without an
    error (#49), which is why this cannot be left to the device.
    """
    coordinator = _coordinator(hass, _cloud("first"))
    coordinator.api.get_device_control_fields.return_value = {
        "Secondary Output Priority Start Time": {"type": "value", "id": "time"}
    }
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "null"}

    (number,) = await _async_build_number_entities(coordinator, set())
    assert number.extra_state_attributes["value_status"] == "not_loaded"

    coordinator.ctrl_value_cache["TEST"]["time"] = "15:30"
    with patch.object(number, "async_write_ha_state"):
        number._handle_coordinator_update()

    assert number.native_value is None
    assert number.extra_state_attributes["value_status"] == "unsupported_format"
    with pytest.raises(ValueError, match="not a number"):
        await number.async_set_native_value(50)
    coordinator.api.set_device_control_value.assert_not_awaited()
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
    """Stopping per-field reads must not strand entities at unknown.

    The reads here answer with a placeholder rather than failing, which is
    the case that retires a field after the short budget: the API spoke, and
    it has no value to give. A read that fails outright is a different case
    with its own budget, exercised below.
    """
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "null"}
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


async def test_a_read_that_fails_keeps_its_longer_budget(hass):
    """A field that answers one round in three must not be retired after three.

    On the hardware in #60 nine control values timed out during startup and
    every one of those entities stayed unknown. The reads were flaky, not
    unsupported: the same fields answered when asked again. The short budget
    is for a field the API answers with nothing, which settles the question;
    a read that never lands settles nothing, so it gets the longer budget.
    """
    coordinator = _coordinator(hass, _cloud())
    await _async_build_select_entities(coordinator, set())
    await _async_build_number_entities(coordinator, set())
    assert coordinator.api.get_device_control_value.await_count == 2

    for _ in range(MAX_CONTROL_VALUE_RETRIES + 1):
        coordinator.cloud_revision += 1
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    # The short budget would have stopped at three rounds of two reads.
    assert coordinator.api.get_device_control_value.await_count > 2 * (
        MAX_CONTROL_VALUE_RETRIES
    )

    async def read(_pn, _devcode, _address, _sn, field):
        return {"val": "2" if field == "priority" else "17A"}

    coordinator.api.get_device_control_value.side_effect = read
    coordinator.cloud_revision += 1
    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    assert values == {"priority": "2", "current": "17A"}
    assert coordinator._ctrl_value_retries["TEST"] == 0
    await coordinator.async_shutdown()


async def test_a_failing_read_is_still_bounded(hass):
    """A dead API must not be polled for the life of the entry."""
    coordinator = _coordinator(hass, _cloud())
    await _async_build_select_entities(coordinator, set())

    for _ in range(MAX_UNANSWERED_CONTROL_VALUE_RETRIES + 5):
        coordinator.cloud_revision += 1
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    assert coordinator.api.get_device_control_value.await_count == 2 * (
        MAX_UNANSWERED_CONTROL_VALUE_RETRIES
    )
    await coordinator.async_shutdown()


async def test_one_stalled_field_does_not_hold_up_the_round(hass):
    """A read that never returns used to hold entity discovery open.

    The API answers one field per request and a stalled one costs the full
    request timeout, so a device with dozens of fields could outlive Home
    Assistant's startup window with every control on the account unavailable
    (#60). The round now has its own deadline, and what it abandons is
    retried on a later revision rather than waited on.
    """
    coordinator = _coordinator(hass, _cloud())

    async def read(_pn, _devcode, _address, _sn, field):
        if field == "priority":
            await asyncio.sleep(3600)
        return {"val": "17A"}

    coordinator.api.get_device_control_value.side_effect = read

    with patch(
        "custom_components.dessmonitor.CONTROL_VALUE_ROUND_TIMEOUT_SECONDS", 0.05
    ):
        values, unanswered = await coordinator._fetch_all_control_values(
            "PN", 6544, 1, "TEST", ["priority", "current"]
        )

    assert values == {"current": "17A"}
    assert unanswered is True
    await coordinator.async_shutdown()


async def test_cancelling_a_round_leaves_no_reads_running(hass):
    """Unloading the entry cancels discovery mid-round.

    The reads run as their own tasks so the round can have a deadline, which
    means the round owns cancelling them. A task left running after unload
    would keep calling an API client whose session is being closed.
    """
    coordinator = _coordinator(hass, _cloud())
    started: list[str] = []

    async def read(_pn, _devcode, _address, _sn, field):
        started.append(field)
        await asyncio.sleep(3600)

    coordinator.api.get_device_control_value.side_effect = read

    round_task = asyncio.create_task(
        coordinator._fetch_all_control_values(
            "PN", 6544, 1, "TEST", ["priority", "current"]
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert started, "the reads should have begun"

    round_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await round_task

    pending = [
        task
        for task in asyncio.all_tasks()
        if "_fetch_one" in repr(task.get_coro()) and not task.done()
    ]
    assert pending == []
    await coordinator.async_shutdown()


async def test_a_device_without_controls_is_asked_for_its_fields_once(hass):
    """An empty field list is an answer, not a reason to ask again.

    The cache was keyed on a non-empty list, so a collector that carries no
    controls cost one request per cloud revision for the life of the entry.
    """
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_fields.return_value = {}

    for revision in range(1, 6):
        coordinator.cloud_revision = revision
        controls, _values = await coordinator.async_get_controls_with_values(
            "PN", 684, 1, "TEST"
        )
        assert controls == {}

    assert coordinator.api.get_device_control_fields.await_count == 1
    await coordinator.async_shutdown()


async def test_a_refused_control_field_list_is_retired(hass):
    """A grid-tie collector has no control template and never will (#62).

    The platform answers ERR_NO_RECORD every time, so the retries are bounded
    rather than warning once a minute for as long as the entry stays loaded.
    """
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_fields.side_effect = DessMonitorError(
        "ERR_NO_RECORD(no default template)", 4
    )

    for revision in range(1, MAX_CONTROL_FIELD_RETRIES + 6):
        coordinator.cloud_revision = revision
        controls, _values = await coordinator.async_get_controls_with_values(
            "PN", 684, 1, "TEST"
        )
        assert controls == {}

    assert (
        coordinator.api.get_device_control_fields.await_count
        == MAX_CONTROL_FIELD_RETRIES
    )
    await coordinator.async_shutdown()


async def test_a_control_field_list_that_recovers_is_published(hass):
    """The bound must not retire a device whose account is briefly failing."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_fields.side_effect = [
        DessMonitorError("ERR_TIMEOUT", 2),
        DessMonitorError("ERR_TIMEOUT", 2),
        CONTROLS,
    ]

    for revision in range(1, 4):
        coordinator.cloud_revision = revision
        controls, _values = await coordinator.async_get_controls_with_values(
            "PN", 6544, 1, "TEST"
        )

    assert set(controls) == set(CONTROLS)
    assert coordinator._ctrl_field_failures == {}
    await coordinator.async_shutdown()


async def test_exhausting_the_budget_is_reported_once_per_device(hass, caplog):
    """The give-up line is now the only report of an unreadable control (#61).

    The API layer logged every refused attempt at error level, which filled a
    reporter's log with twenty red entries in an hour for a bounded, retried
    condition. Those attempts are debug now, so this line carries the outcome
    and has to be visible by default.
    """
    coordinator = _coordinator(hass, _cloud())
    await _async_build_select_entities(coordinator, set())

    with caplog.at_level(logging.DEBUG, logger="custom_components.dessmonitor"):
        for _ in range(MAX_UNANSWERED_CONTROL_VALUE_RETRIES + 5):
            coordinator.cloud_revision += 1
            await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.getMessage().startswith("Giving up on")
    ]
    assert len(warnings) == 1
    assert "TEST" in warnings[0].getMessage()
    await coordinator.async_shutdown()


async def test_the_download_says_whether_reads_have_been_given_up_on(hass):
    """A control reading unknown looks the same either way (#61).

    Whether the next refresh will ask again or the budget ran out rounds ago
    is the first question behind a control that never recovers, and the file
    could not answer it.
    """
    from custom_components.dessmonitor import (
        MAX_UNANSWERED_CONTROL_VALUE_RETRIES,
        _build_device_support_report,
    )

    data = _cloud("first")
    coordinator = _coordinator(hass, data)
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    entry = MagicMock(entry_id="entry", data={"username": "u"}, options={})

    async def _state():
        report = await _build_device_support_report(
            coordinator, entry, "TEST", coordinator.data["TEST"]
        )
        return report["control_reads"]

    # Every read times out, so each round spends one of the twelve allowed.
    for round_number in range(MAX_UNANSWERED_CONTROL_VALUE_RETRIES):
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
        state = await _state()
        assert state["last_round_went_unanswered"] is True
        assert state["rounds_allowed"] == MAX_UNANSWERED_CONTROL_VALUE_RETRIES
        if state["rounds_that_recovered_nothing"] >= state["rounds_allowed"]:
            break
        assert state["still_trying"] is True
        coordinator.cloud_revision += 1

    state = await _state()
    assert state["still_trying"] is False
    assert state["without_a_value"] == state["fields"]


async def test_an_answer_outside_the_options_is_not_asked_for_again(hass):
    """A control the API answers outside its option list is answered, not unread.

    The log in #53 read "Fetched 1/2 control values" on three consecutive
    rounds while both controls stayed unknown and the diagnostics file said
    "Not read" for them. The answer was being discarded because none of the
    control's options matched it, so the field looked as though it had never
    been read and was re-read for the whole budget.
    """
    coordinator = _coordinator(hass, _cloud())

    async def read(_pn, _devcode, _address, _sn, field):
        # 9 is not one of this control's options, which are 1 and 2.
        return {"val": "9"} if field == "priority" else {"val": "17A"}

    coordinator.api.get_device_control_value.side_effect = read
    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    reads = coordinator.api.get_device_control_value.await_count
    assert coordinator.ctrl_unmatched_values["TEST"] == {"priority": "9"}

    for revision in range(2, 6):
        coordinator.cloud_revision = revision
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert coordinator.api.get_device_control_value.await_count == reads
    await coordinator.async_shutdown()


async def test_the_diagnostics_file_says_what_was_read(hass):
    """"Not read" and "read, and no option matches" are opposite diagnoses."""
    from custom_components.dessmonitor import _known_control_values

    coordinator = _coordinator(hass, _cloud())
    coordinator.ctrl_unmatched_values["TEST"] = {"priority": "9"}
    coordinator.ctrl_value_cache["TEST"] = {"current": "17A"}

    reported = _known_control_values(coordinator, "TEST")

    assert reported["current"] == "17A"
    assert reported["priority"].startswith("9 (")
    assert "not one of the options" in reported["priority"]
    await coordinator.async_shutdown()


async def test_a_fresh_field_list_forgets_what_matched_nothing(hass):
    """A new option list can offer what the old one did not."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.ctrl_unmatched_values["TEST"] = {"priority": "9"}

    assert await coordinator._async_cache_control_fields("PN", 6544, 1, "TEST")
    assert "TEST" not in coordinator.ctrl_unmatched_values
    await coordinator.async_shutdown()


async def test_a_setting_changed_outside_home_assistant_is_read_again(hass):
    """A known control value was read once and then frozen (#53).

    The retry rounds read only the fields with no value, and ordinary
    telemetry refreshes only those a collector repeats among its readings. So
    the account in #53 showed Back To Grid Voltage at 46 V while the vendor
    app showed 48, and Max Charging Current at 40 A against 100, with nothing
    in the integration able to notice either.
    """
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "460"}
    coordinator.ctrl_field_cache["TEST"] = {
        "Back To Grid Voltage": {
            "type": "options",
            "id": "bat_battery_charging_voltage",
            "options": {"460": "46.0", "480": "48.0"},
        }
    }

    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert values["bat_battery_charging_voltage"] == "460"

    # The owner sets 48.0 V in the vendor app.
    coordinator.api.get_device_control_value.return_value = {"val": "480"}
    _age_field(coordinator, "TEST", "bat_battery_charging_voltage")
    coordinator.cloud_revision += 1

    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    assert values["bat_battery_charging_voltage"] == "480"
    await coordinator.async_shutdown()


async def test_a_refresh_is_held_off_a_field_just_written(hass):
    """Reading a field back before the inverter has acted on it bounces it."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "460"}
    coordinator.ctrl_field_cache["TEST"] = {
        "Back To Grid Voltage": {
            "type": "options",
            "id": "bat_battery_charging_voltage",
            "options": {"460": "46.0", "480": "48.0"},
        }
    }
    coordinator.record_control_write("TEST", "bat_battery_charging_voltage", "480")
    _age_field(coordinator, "TEST", "bat_battery_charging_voltage")
    coordinator.cloud_revision += 1

    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    assert values["bat_battery_charging_voltage"] == "480"
    coordinator.api.get_device_control_value.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_a_refresh_never_reads_a_field_telemetry_already_carries(hass):
    """Those refresh themselves on every cloud sample, so a read buys nothing.

    This is the difference between a few reads an hour and a permanent
    trickle of them down a link that carries one transaction at a time (#61).
    """
    coordinator = _coordinator(
        hass, _cloud("first", _point("Main Output Priority", "SBU"))
    )
    (select,) = await _async_build_select_entities(coordinator, set())
    assert select.current_option == "SBU"
    coordinator.api.get_device_control_value.reset_mock()
    _age_field(coordinator, "TEST", "priority")
    coordinator.cloud_revision += 1

    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    assert "priority" not in [
        call.args[-1] for call in coordinator.api.get_device_control_value.await_args_list
    ]
    await coordinator.async_shutdown()


async def test_a_refresh_keeps_the_value_the_entity_shows_when_a_read_fails(hass):
    """A failed or unmatched read must not blank a setting that reads fine."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "460"}
    coordinator.ctrl_field_cache["TEST"] = {
        "Back To Grid Voltage": {
            "type": "options",
            "id": "bat_battery_charging_voltage",
            "options": {"460": "46.0", "480": "48.0"},
        }
    }
    _, values = await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert values["bat_battery_charging_voltage"] == "460"

    for answer, side_effect in (
        ({"val": "540"}, None),
        (None, DessMonitorError("ERR_TIMEOUT", 2)),
    ):
        coordinator.api.get_device_control_value.return_value = answer
        coordinator.api.get_device_control_value.side_effect = side_effect
        _age_field(coordinator, "TEST", "bat_battery_charging_voltage")
        coordinator.cloud_revision += 1
        _, values = await coordinator.async_get_controls_with_values(
            "PN", 6544, 1, "TEST"
        )
        assert values["bat_battery_charging_voltage"] == "460"

    assert (
        coordinator.ctrl_unmatched_values["TEST"]["bat_battery_charging_voltage"]
        == "540"
    )
    await coordinator.async_shutdown()


async def test_a_refresh_reads_no_more_than_its_cap_per_revision(hass):
    """The rotation is the whole reason this costs little; cap it (#61)."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "1"}
    coordinator.ctrl_field_cache["TEST"] = {
        f"Setting {index}": {
            "type": "options",
            "id": f"field_{index}",
            "options": {"1": "On", "2": "Off"},
        }
        for index in range(8)
    }
    coordinator.ctrl_value_cache["TEST"] = {
        f"field_{index}": "1" for index in range(8)
    }
    for index in range(8):
        _age_field(coordinator, "TEST", f"field_{index}")
    coordinator.cloud_revision += 1

    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    assert coordinator.api.get_device_control_value.await_count == (
        CONTROL_VALUE_REFRESH_PER_ROUND
    )
    await coordinator.async_shutdown()


async def test_a_device_still_missing_values_spends_nothing_on_refreshing(hass):
    """Recovery keeps priority, so startup behaviour is unchanged."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "null"}
    coordinator.ctrl_field_cache["TEST"] = {
        "Known": {"type": "options", "id": "known", "options": {"1": "On", "2": "Off"}},
        "Unknown": {
            "type": "options",
            "id": "unknown",
            "options": {"1": "On", "2": "Off"},
        },
    }
    coordinator.ctrl_value_cache["TEST"] = {"known": "1"}
    _age_field(coordinator, "TEST", "known")
    coordinator.cloud_revision += 1

    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    read = [
        call.args[-1]
        for call in coordinator.api.get_device_control_value.await_args_list
    ]
    assert read == ["unknown"]
    await coordinator.async_shutdown()


async def test_a_field_read_recently_is_not_read_again(hass):
    """The minimum age is what keeps a small control set from being re-read
    on every cloud revision, which would be twelve live reads an hour for a
    setting nobody changes (#53)."""
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "460"}
    coordinator.ctrl_field_cache["TEST"] = {
        "Back To Grid Voltage": {
            "type": "options",
            "id": "bat_battery_charging_voltage",
            "options": {"460": "46.0", "480": "48.0"},
        }
    }
    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    coordinator.api.get_device_control_value.reset_mock()

    for _ in range(5):
        coordinator.cloud_revision += 1
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    coordinator.api.get_device_control_value.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_a_control_the_hardware_moves_is_followed_closely(hass):
    """Not every control is a setting somebody chose (#53).

    The inverter negotiates Max Charging Current with the battery BMS and
    moves it on its own, so the reporter saw 40 A against the app's 100 while
    the forty settings around it had not changed in months. A fixed rotation
    is wrong for both: each field earns its own interval from whether reading
    it has found anything new.
    """
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "040"}
    coordinator.ctrl_field_cache["TEST"] = {
        "Max Charging Current": {
            "type": "options",
            "id": "bat_max_charging_current",
            "options": {"040": "40.0", "100": "100.0"},
        }
    }
    field = ("TEST", "bat_max_charging_current")

    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
    assert coordinator.ctrl_value_cache["TEST"]["bat_max_charging_current"] == "040"

    # The BMS raises the limit, and the next refresh finds it.
    coordinator.api.get_device_control_value.return_value = {"val": "100"}
    _age_field(coordinator, *field)
    coordinator.cloud_revision += 1
    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    assert coordinator.ctrl_value_cache["TEST"]["bat_max_charging_current"] == "100"
    assert (
        coordinator._ctrl_refresh_interval[field]
        == CONTROL_VALUE_REFRESH_FAST_INTERVAL_SECONDS
    )

    # It is now read on the short interval rather than the base one.
    coordinator._ctrl_value_read_at[field] = (
        dessmonitor.monotonic() - CONTROL_VALUE_REFRESH_FAST_INTERVAL_SECONDS - 1
    )
    coordinator.api.get_device_control_value.reset_mock()
    coordinator.cloud_revision += 1
    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    coordinator.api.get_device_control_value.assert_awaited_once()
    await coordinator.async_shutdown()


async def test_a_control_nobody_touches_is_read_less_and_less(hass):
    """A read that finds nothing new earns the field a longer interval.

    Otherwise forty unchanging settings would cost the same live reads for
    the life of the entry, down a link that carries one transaction at a
    time (#61).
    """
    coordinator = _coordinator(hass, _cloud())
    coordinator.api.get_device_control_value.side_effect = None
    coordinator.api.get_device_control_value.return_value = {"val": "040"}
    coordinator.ctrl_field_cache["TEST"] = {
        "Max Charging Current": {
            "type": "options",
            "id": "bat_max_charging_current",
            "options": {"040": "40.0", "100": "100.0"},
        }
    }
    field = ("TEST", "bat_max_charging_current")
    await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")

    intervals = []
    for _ in range(4):
        _age_field(coordinator, *field)
        coordinator._ctrl_value_read_at[field] -= (
            CONTROL_VALUE_REFRESH_MAX_INTERVAL_SECONDS
        )
        coordinator.cloud_revision += 1
        await coordinator.async_get_controls_with_values("PN", 6544, 1, "TEST")
        intervals.append(coordinator._ctrl_refresh_interval[field])

    assert intervals == sorted(intervals)
    assert intervals[0] == CONTROL_VALUE_REFRESH_BASE_INTERVAL_SECONDS * 2
    assert intervals[-1] <= CONTROL_VALUE_REFRESH_MAX_INTERVAL_SECONDS
    await coordinator.async_shutdown()
