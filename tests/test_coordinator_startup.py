"""Startup performance regressions for the cloud coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator


async def test_telemetry_refresh_does_not_wait_for_control_value_reads(
    hass: HomeAssistant,
) -> None:
    """Per-field control reads must not delay cloud or hybrid telemetry setup."""
    api = MagicMock()
    api.close = AsyncMock()
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    payload = {
        "DEVICE": {
            "collector": {"pn": "COLLECTOR"},
            "device": {"devcode": 2376, "devaddr": 1},
            "data": [],
        }
    }
    coordinator.async_get_controls_with_values = AsyncMock()

    try:
        with (
            patch.object(coordinator, "_fetch_collectors", AsyncMock(return_value=[])),
            patch.object(
                coordinator,
                "_gather_all_device_data",
                AsyncMock(return_value=payload),
            ),
            patch.object(coordinator, "_merge_summary_data", AsyncMock()),
            patch.object(coordinator, "_async_store_cloud_snapshot", AsyncMock()),
        ):
            result = await coordinator._async_update_data()
    finally:
        await coordinator.async_shutdown()

    assert result["DEVICE"]["data"][-1] == {
        "title": "Data Source",
        "val": "Cloud",
        "unit": "",
    }
    coordinator.async_get_controls_with_values.assert_not_awaited()


async def test_duplicate_project_collectors_are_polled_once(
    hass: HomeAssistant,
) -> None:
    """Repeated PN rows must not duplicate device discovery and telemetry calls."""
    api = AsyncMock()
    api.get_collectors.return_value = (
        [{"pn": "SHARED", "pid": 1}, {"pn": "SHARED", "pid": 2}],
        [],
    )
    api.get_collector_devices.return_value = {
        "dev": [{"sn": "INVERTER", "devcode": 6544, "devaddr": 1}]
    }
    api.get_device_last_data.return_value = [
        {"title": "Battery Voltage", "val": "53.1", "unit": "V"}
    ]
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    try:
        with patch.object(coordinator, "_merge_summary_data", AsyncMock()):
            data = await coordinator._async_update_data()
        api.get_collector_devices.assert_awaited_once_with("SHARED")
        api.get_device_last_data.assert_awaited_once()
        assert data["INVERTER"]["collector"] == {"pn": "SHARED", "pid": 2}
        assert data["INVERTER"]["data"][0]["val"] == "53.1"
    finally:
        await coordinator.async_shutdown()


async def test_distinct_collectors_are_retained(hass: HomeAssistant) -> None:
    api = AsyncMock()
    api.get_collectors.return_value = (
        [{"pn": "A", "pid": 1}, {"pn": "B", "pid": 1}, {"pn": "A", "pid": 2}],
        [],
    )
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    try:
        assert await coordinator._fetch_collectors() == [
            {"pn": "A", "pid": 2},
            {"pn": "B", "pid": 1},
        ]
    finally:
        await coordinator.async_shutdown()
