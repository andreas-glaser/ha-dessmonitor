"""Tests for preferred-local data merging and cloud fallback."""

from __future__ import annotations

import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
from custom_components.dessmonitor.const import (
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_COLLECTOR_IPS,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
)
from custom_components.dessmonitor.local.hybrid import (
    DessMonitorHybridCoordinator,
    merge_cloud_and_local,
)


def _cloud_payload() -> dict:
    return {
        "CLOUD-SERIAL": {
            "collector": {"pn": "COLLECTOR-1"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Main"},
            "data": [
                {"title": "Grid voltage", "val": 228, "unit": "V"},
                {"title": "AC output active power", "val": 700, "unit": "W"},
                {"title": "Cloud only", "val": 123, "unit": ""},
            ],
        }
    }


def _local_payload() -> dict:
    return {
        "LOCAL-SERIAL": {
            "collector": {"pn": "COLLECTOR-1"},
            "device": {"devcode": 2452, "devaddr": 1},
            "data": [
                {"title": "Grid Voltage", "val": 231.2, "unit": "V"},
                {"title": "Output Active Power", "val": 900, "unit": "W"},
            ],
        }
    }


def test_healthy_local_values_overlay_matching_cloud_device() -> None:
    """The cloud entity identity is retained while local values win by title."""
    merged = merge_cloud_and_local(
        _cloud_payload(), _local_payload(), local_available=True
    )

    assert set(merged) == {"CLOUD-SERIAL"}
    points = {point["title"]: point["val"] for point in merged["CLOUD-SERIAL"]["data"]}
    assert points["Grid Voltage"] == 231.2
    assert points["Output Active Power"] == 900
    assert points["Cloud only"] == 123
    assert points["Data Source"] == "Local"


def test_local_outage_falls_back_to_cloud_values() -> None:
    """Unhealthy local state is never served as current telemetry."""
    merged = merge_cloud_and_local(
        _cloud_payload(), _local_payload(), local_available=False
    )
    points = {point["title"]: point["val"] for point in merged["CLOUD-SERIAL"]["data"]}
    assert points["Grid voltage"] == 228
    assert points["AC output active power"] == 700
    assert points["Data Source"] == "Cloud"


def test_unrelated_collector_is_not_overlaid() -> None:
    """An unrelated local device cannot create a second hybrid identity."""
    local = _local_payload()
    local["LOCAL-SERIAL"]["collector"]["pn"] = "OTHER-COLLECTOR"
    merged = merge_cloud_and_local(_cloud_payload(), local, local_available=True)

    assert set(merged) == {"CLOUD-SERIAL"}
    cloud_points = {
        point["title"]: point["val"] for point in merged["CLOUD-SERIAL"]["data"]
    }
    assert cloud_points["Grid voltage"] == 228
    assert cloud_points["Data Source"] == "Cloud"


def test_local_only_snapshot_waits_for_canonical_cloud_identity() -> None:
    """Hybrid never invents entity IDs before the API or cache can map them."""
    assert merge_cloud_and_local({}, _local_payload(), local_available=True) == {}


def test_merge_does_not_mutate_coordinator_snapshots() -> None:
    """Push updates can safely reuse source snapshots across refreshes."""
    cloud = _cloud_payload()
    local = _local_payload()
    original_cloud = copy.deepcopy(cloud)
    original_local = copy.deepcopy(local)

    merge_cloud_and_local(cloud, local, local_available=True)

    assert cloud == original_cloud
    assert local == original_local


def test_partial_local_availability_falls_back_per_collector() -> None:
    """One failed local route cannot demote healthy routes or lose cloud data."""
    cloud = _cloud_payload()
    cloud["SECOND-CLOUD-SERIAL"] = {
        "collector": {"pn": "COLLECTOR-2"},
        "device": {"devcode": 2452, "devaddr": 1, "alias": "Second"},
        "data": [{"title": "Grid voltage", "val": 229, "unit": "V"}],
    }

    merged = merge_cloud_and_local(cloud, _local_payload(), local_available=True)
    first = {
        point["title"]: point["val"]
        for point in merged["CLOUD-SERIAL"]["data"]
    }
    second = {
        point["title"]: point["val"]
        for point in merged["SECOND-CLOUD-SERIAL"]["data"]
    }

    assert first["Data Source"] == "Local"
    assert first["Grid Voltage"] == 231.2
    assert second["Data Source"] == "Cloud"
    assert second["Grid voltage"] == 229


def _hybrid_coordinator(hass: HomeAssistant) -> DessMonitorHybridCoordinator:
    """Create a hybrid coordinator without opening sockets."""
    api = MagicMock()
    api.token = "token"
    api.secret = "secret"
    api.close = AsyncMock()
    return DessMonitorHybridCoordinator(
        hass,
        api,
        300,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.2",
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
        },
        "hybrid-test",
    )


async def test_cloud_outage_keeps_healthy_local_data(hass: HomeAssistant) -> None:
    """A cloud failure never makes fresh local telemetry unavailable."""
    coordinator = _hybrid_coordinator(hass)
    coordinator._cached_cloud_data = _cloud_payload()
    coordinator.local.async_set_updated_data(_local_payload())
    try:
        with patch.object(
            DessMonitorDataUpdateCoordinator,
            "_async_update_data",
            new=AsyncMock(side_effect=UpdateFailed("cloud unavailable")),
        ):
            result = await coordinator._async_update_data()
        points = {
            point["title"]: point["val"]
            for point in result["CLOUD-SERIAL"]["data"]
        }
        assert points["Output Active Power"] == 900
        assert points["Data Source"] == "Local"
    finally:
        await coordinator.async_shutdown()


async def test_local_data_arriving_during_cloud_timeout_is_used(
    hass: HomeAssistant,
) -> None:
    """A slow failed API request cannot hide a collector that connected meanwhile."""
    coordinator = _hybrid_coordinator(hass)
    coordinator._cached_cloud_data = _cloud_payload()

    async def _cloud_failure_after_local_arrives(*_args: object) -> dict:
        coordinator.local.async_set_updated_data(_local_payload())
        raise UpdateFailed("cloud unavailable")

    try:
        with patch.object(
            DessMonitorDataUpdateCoordinator,
            "_async_update_data",
            new=_cloud_failure_after_local_arrives,
        ):
            result = await coordinator._async_update_data()
        points = {
            point["title"]: point["val"]
            for point in result["CLOUD-SERIAL"]["data"]
        }
        assert points["Grid Voltage"] == 231.2
        assert points["Data Source"] == "Local"
    finally:
        await coordinator.async_shutdown()


async def test_both_outages_keep_last_cloud_snapshot(hass: HomeAssistant) -> None:
    """A transient double outage preserves history with an explicit stale source."""
    coordinator = _hybrid_coordinator(hass)
    coordinator._cached_cloud_data = _cloud_payload()
    coordinator.local.async_set_update_error(UpdateFailed("local unavailable"))
    try:
        with patch.object(
            DessMonitorDataUpdateCoordinator,
            "_async_update_data",
            new=AsyncMock(side_effect=UpdateFailed("cloud unavailable")),
        ):
            result = await coordinator._async_update_data()
        points = {
            point["title"]: point["val"]
            for point in result["CLOUD-SERIAL"]["data"]
        }
        assert points["Grid voltage"] == 228
        assert points["Data Source"] == "Cached Cloud"
    finally:
        await coordinator.async_shutdown()


async def test_cloud_outage_marks_each_unmatched_device_as_cached(
    hass: HomeAssistant,
) -> None:
    """A healthy local route cannot make another device's stale API data look live."""
    coordinator = _hybrid_coordinator(hass)
    cloud = _cloud_payload()
    cloud["SECOND-CLOUD-SERIAL"] = {
        "collector": {"pn": "COLLECTOR-2"},
        "device": {"devcode": 2452, "devaddr": 1},
        "data": [{"title": "Grid voltage", "val": 229, "unit": "V"}],
    }
    coordinator._cached_cloud_data = cloud
    coordinator.local.async_set_updated_data(_local_payload())
    try:
        with patch.object(
            DessMonitorDataUpdateCoordinator,
            "_async_update_data",
            new=AsyncMock(side_effect=UpdateFailed("cloud unavailable")),
        ):
            result = await coordinator._async_update_data()
        first = {
            point["title"]: point["val"]
            for point in result["CLOUD-SERIAL"]["data"]
        }
        second = {
            point["title"]: point["val"]
            for point in result["SECOND-CLOUD-SERIAL"]["data"]
        }
        assert first["Data Source"] == "Local"
        assert second["Data Source"] == "Cached Cloud"
    finally:
        await coordinator.async_shutdown()


async def test_hybrid_shutdown_is_idempotent(hass: HomeAssistant) -> None:
    """Reload cleanup closes each owned resource exactly once."""
    coordinator = _hybrid_coordinator(hass)
    coordinator.local.async_shutdown = AsyncMock()
    await coordinator.async_shutdown()
    await coordinator.async_shutdown()
    coordinator.local.async_shutdown.assert_awaited_once()
    coordinator.api.close.assert_awaited_once()


async def test_hybrid_coalesces_simultaneous_collector_pushes(
    hass: HomeAssistant,
) -> None:
    """Local pushes coalesce without postponing the cloud refresh timer."""
    coordinator = _hybrid_coordinator(hass)
    coordinator._initial_refresh_completed = True
    coordinator._cached_cloud_data = _cloud_payload()
    coordinator.local.async_set_updated_data(_local_payload())
    listener = MagicMock()
    remove_listener = coordinator.async_add_listener(listener)
    scheduled_cloud_refresh = coordinator._unsub_refresh
    assert scheduled_cloud_refresh is not None
    try:
        coordinator._handle_local_update()
        coordinator._handle_local_update()
        coordinator._handle_local_update()
        await asyncio.sleep(0.15)
        listener.assert_called_once()
        assert coordinator._unsub_refresh is scheduled_cloud_refresh
        assert coordinator.data is not None
        points = {
            point["title"]: point["val"]
            for point in coordinator.data["CLOUD-SERIAL"]["data"]
        }
        assert points["Data Source"] == "Local"
    finally:
        remove_listener()
        await coordinator.async_shutdown()


def test_hybrid_builds_one_local_route_per_collector(hass: HomeAssistant) -> None:
    """One cloud entry can prefer local telemetry for every configured collector."""
    api = MagicMock(token="token", secret="secret", close=AsyncMock())
    coordinator = DessMonitorHybridCoordinator(
        hass,
        api,
        300,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IPS: ["127.0.0.2", "127.0.0.3", "127.0.0.2"],
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
        },
        "multi-hybrid-test",
    )
    assert [local._server.allowed_peer_ip for local in coordinator.locals] == [
        "127.0.0.2",
        "127.0.0.3",
    ]


def test_hybrid_coordinator_is_attached_to_config_entry(
    hass: HomeAssistant,
) -> None:
    """HA first-refresh lifecycle requires the owning config entry."""
    api = MagicMock(token="token", secret="secret", close=AsyncMock())
    entry = MagicMock()
    coordinator = DessMonitorHybridCoordinator(
        hass,
        api,
        300,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.2",
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
        },
        "attached-hybrid-test",
        config_entry=entry,
    )
    assert coordinator.config_entry is entry
