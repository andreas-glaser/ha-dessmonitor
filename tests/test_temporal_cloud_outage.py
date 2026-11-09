"""Temporal controls compose with per-device retention introduced in 2.6.0."""

from copy import deepcopy
from datetime import time
from unittest.mock import patch

import pytest

from custom_components.dessmonitor import MAX_CONTROL_VALUE_RETRIES
from custom_components.dessmonitor.api import DessMonitorError

from .test_temporal_controls import FIELDS, _coordinator, _entities


def _configure_cloud_reads(coordinator, *, second_device=False):
    coordinator.api.get_collectors.return_value = ([{"pn": "PN"}], [])
    devices = [{"sn": "TEST", "devcode": 6544, "devaddr": 1}]
    if second_device:
        devices.append({"sn": "OTHER", "devcode": 6544, "devaddr": 2})
    coordinator.api.get_collector_devices.return_value = {"dev": devices}
    coordinator.api.get_device_parameters.return_value = {}
    coordinator.api.get_device_summary_data.return_value = {}
    coordinator.api._make_request.return_value = {"dat": {"plant": []}}


async def _refresh(coordinator):
    # Run the production gather/retain/revision paths, not a mocked snapshot merge.
    result = await coordinator._async_update_data()
    coordinator.async_set_updated_data(result)
    return result


def _source(result, serial="TEST"):
    return next(p["val"] for p in result[serial]["data"] if p["title"] == "Data Source")


@pytest.mark.parametrize("kind", ["time", "text"])
async def test_total_cloud_failure_preserves_temporal_retry_budget(hass, kind):
    coordinator = _coordinator(hass, values=False)
    _configure_cloud_reads(coordinator)
    known = set()
    entity = (await _entities(coordinator, kind, known))[0]
    initial_reads = coordinator.api.get_device_control_value.await_count
    assert initial_reads == len(FIELDS)
    assert coordinator._ctrl_value_retries["TEST"] == 1
    revision = coordinator.cloud_revision
    baseline = deepcopy(coordinator._cached_cloud_data)
    coordinator.api.get_device_last_data.side_effect = DessMonitorError(
        "Request timed out"
    )
    try:
        with patch.object(entity, "async_write_ha_state"):
            unsubscribe = coordinator.async_add_listener(
                entity._handle_coordinator_update
            )
            try:
                for _ in range(MAX_CONTROL_VALUE_RETRIES + 2):
                    result = await _refresh(coordinator)
                    assert _source(result) == "Cached Cloud"
                    assert coordinator.cloud_revision == revision
                    assert coordinator._cached_cloud_data == baseline
                    assert await _entities(coordinator, kind, known) == []
                    assert coordinator._ctrl_value_retries["TEST"] == 1
                    assert (
                        coordinator.api.get_device_control_value.await_count
                        == initial_reads
                    )
                    assert entity.native_value is None

                # An actual successful refresh still allows missing-value recovery.
                coordinator.api.get_device_last_data.side_effect = None
                coordinator.api.get_device_last_data.return_value = [
                    {"title": "Timestamp", "val": "recovered"},
                    *[{"title": name, "val": raw} for name, (_, raw) in FIELDS.items()],
                ]
                result = await _refresh(coordinator)
                assert _source(result) == "Cloud"
                assert coordinator.cloud_revision == revision + 1
                assert entity.native_value == (
                    time(15) if kind == "time" else "2026-10-13 13:36:16"
                )
                assert (
                    coordinator.api.get_device_control_value.await_count
                    == initial_reads
                )
                coordinator.api.set_device_control_value.assert_not_awaited()
            finally:
                unsubscribe()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "kind,accepted", [("time", time(16, 45)), ("text", "2026-10-31 12:34:56")]
)
async def test_retained_old_sample_does_not_revert_accepted_temporal_value(
    hass, kind, accepted
):
    coordinator = _coordinator(hass)
    _configure_cloud_reads(coordinator, second_device=True)
    entity = (await _entities(coordinator, kind))[0]
    original = entity.native_value
    baseline = deepcopy(coordinator._cached_cloud_data["TEST"]["data"])

    async def one_device_fails(**kwargs):
        if kwargs["sn"] == "TEST":
            raise DessMonitorError("Request timed out")
        return [{"title": "Timestamp", "val": "other-fresh"}]

    coordinator.api.get_device_last_data.side_effect = one_device_fails
    revision = coordinator.cloud_revision
    try:
        with patch.object(entity, "async_write_ha_state"):
            # API is mocked: this is not hardware write/readback evidence.
            await entity.async_set_value(accepted)
            unsubscribe = coordinator.async_add_listener(
                entity._handle_coordinator_update
            )
            try:
                for _ in range(3):
                    result = await _refresh(coordinator)
                    assert _source(result) == "Cached Cloud"
                    assert _source(result, "OTHER") == "Cloud"
                    assert coordinator.stale_cloud_serials == frozenset({"TEST"})
                    assert coordinator._cached_cloud_data["TEST"]["data"] == baseline
                    assert entity.native_value == accepted
                assert coordinator.cloud_revision == revision + 3
                coordinator.api.get_device_control_value.assert_not_awaited()
                assert coordinator.api.set_device_control_value.await_count == 1

                # Fresh telemetry may legitimately report a different setting.
                coordinator.api.get_device_last_data.side_effect = None
                coordinator.api.get_device_last_data.return_value = [
                    {"title": "Timestamp", "val": "new-real-sample"},
                    *baseline[1:],
                ]
                result = await _refresh(coordinator)
                assert _source(result) == "Cloud"
                assert entity.native_value == original
                assert not coordinator.stale_cloud_serials
            finally:
                unsubscribe()
    finally:
        await coordinator.async_shutdown()
