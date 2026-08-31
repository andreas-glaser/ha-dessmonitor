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
