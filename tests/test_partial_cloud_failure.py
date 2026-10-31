"""A cloud cycle that loses one device must not lose that device's entities.

Issue #55 (hybrid, one collector, one inverter) and #54 (cloud-only, two
collectors) are the same failure: a device that errors in the current cycle is
dropped from the snapshot, so its entities read nothing even though the local
collector or the previous cloud payload still has its values.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
from custom_components.dessmonitor.api import DessMonitorAPI, DessMonitorError
from custom_components.dessmonitor.const import (
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
)
from custom_components.dessmonitor.local.hybrid import DessMonitorHybridCoordinator

COLLECTOR_PN = "Q0024TESTPN"
DEVICE_SN = "5535TESTSN"
SECOND_PN = "Q0099TESTPN"
SECOND_SN = "5599TESTSN"

LIVE_POINTS = [{"title": "Battery Voltage", "val": "26.1", "unit": "V"}]


def _collector(pn: str = COLLECTOR_PN) -> dict[str, Any]:
    return {"pn": pn, "alias": "Datalogger"}


def _device(sn: str = DEVICE_SN) -> dict[str, Any]:
    return {"sn": sn, "devcode": 2452, "devaddr": 1, "alias": "Inverter"}


def _cloud_api(*collectors: dict[str, Any]) -> MagicMock:
    """A cloud client whose per-device call can be made to fail."""
    api = create_autospec(DessMonitorAPI, instance=True)
    api.token = "token"
    api.secret = "secret"
    api.get_collectors.return_value = (list(collectors), [])
    api.get_device_summary_data.return_value = {}
    return api


def _local_payload(sn: str = "LOCAL-SERIAL") -> dict[str, Any]:
    return {
        sn: {
            "collector": {"pn": COLLECTOR_PN},
            "device": {"devcode": 2452, "devaddr": 1},
            "data": [{"title": "Battery Voltage", "val": 26.4, "unit": "V"}],
        }
    }


@pytest.fixture
def cloud_coordinator(hass: HomeAssistant) -> DessMonitorDataUpdateCoordinator:
    """A cloud-only coordinator over one collector holding one device."""
    api = _cloud_api(_collector())
    api.get_collector_devices.return_value = {"dev": [_device()]}
    return DessMonitorDataUpdateCoordinator(hass, api, 300, entry_id="partial-test")


async def test_device_timeout_keeps_the_previous_payload(
    cloud_coordinator: DessMonitorDataUpdateCoordinator,
) -> None:
    """The one device times out, so its last known payload must carry forward."""
    api = cloud_coordinator.api
    api.get_device_last_data.return_value = LIVE_POINTS

    first = await cloud_coordinator._async_update_data()
    assert DEVICE_SN in first

    api.get_device_last_data.side_effect = DessMonitorError("Request timed out")
    second = await cloud_coordinator._async_update_data()

    assert DEVICE_SN in second, "the device disappeared from the snapshot"
    points = {point["title"]: point["val"] for point in second[DEVICE_SN]["data"]}
    assert points["Battery Voltage"] == "26.1"
    assert points["Data Source"] == "Cached Cloud"


async def test_device_timeout_keeps_the_stored_snapshot(
    cloud_coordinator: DessMonitorDataUpdateCoordinator,
) -> None:
    """An empty cycle must not overwrite the snapshot the fallback relies on."""
    api = cloud_coordinator.api
    api.get_device_last_data.return_value = LIVE_POINTS
    await cloud_coordinator._async_update_data()

    api.get_device_last_data.side_effect = DessMonitorError("Request timed out")
    await cloud_coordinator._async_update_data()

    assert DEVICE_SN in cloud_coordinator._cached_cloud_data


async def test_device_removed_from_the_account_is_dropped(
    cloud_coordinator: DessMonitorDataUpdateCoordinator,
) -> None:
    """Carrying a payload forward must not resurrect a device that is really gone."""
    api = cloud_coordinator.api
    api.get_device_last_data.return_value = LIVE_POINTS
    await cloud_coordinator._async_update_data()

    api.get_collector_devices.return_value = {"dev": []}
    result = await cloud_coordinator._async_update_data()

    assert DEVICE_SN not in result


async def test_one_failing_collector_keeps_its_devices(
    hass: HomeAssistant,
) -> None:
    """Issue #54: a slave collector timing out must not drop its inverter."""
    api = _cloud_api(_collector(), _collector(SECOND_PN))
    api.get_collector_devices.side_effect = lambda pn: {
        COLLECTOR_PN: {"dev": [_device()]},
        SECOND_PN: {"dev": [_device(SECOND_SN)]},
    }[pn]
    api.get_device_last_data.return_value = LIVE_POINTS
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300, entry_id="two-pn")

    first = await coordinator._async_update_data()
    assert {DEVICE_SN, SECOND_SN} <= set(first)

    def _second_collector_times_out(pn: str) -> dict[str, Any]:
        if pn == SECOND_PN:
            raise DessMonitorError("Request timed out")
        return {"dev": [_device()]}

    api.get_collector_devices.side_effect = _second_collector_times_out
    second = await coordinator._async_update_data()

    assert SECOND_SN in second, "the second inverter disappeared from the snapshot"
    sources = {
        sn: {p["title"]: p["val"] for p in payload["data"]}["Data Source"]
        for sn, payload in second.items()
    }
    assert sources == {DEVICE_SN: "Cloud", SECOND_SN: "Cached Cloud"}


async def test_every_device_failing_raises_so_the_fallback_runs(
    cloud_coordinator: DessMonitorDataUpdateCoordinator,
) -> None:
    """With nothing cached yet, a total failure must be reported, not reported empty."""
    api = cloud_coordinator.api
    api.get_device_last_data.side_effect = DessMonitorError("Request timed out")

    with pytest.raises(Exception) as failure:
        await cloud_coordinator._async_update_data()

    assert "timed out" in str(failure.value)


async def test_hybrid_device_timeout_keeps_local_telemetry(
    hass: HomeAssistant,
) -> None:
    """Issue #55: local data every 5s must survive a per-device cloud timeout."""
    api = _cloud_api(_collector())
    api.get_collector_devices.return_value = {"dev": [_device()]}
    api.get_device_last_data.return_value = LIVE_POINTS
    api.close = AsyncMock()
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
        "hybrid-partial",
    )
    try:
        await coordinator._async_update_data()
        coordinator.local.async_set_updated_data(_local_payload())

        api.get_device_last_data.side_effect = DessMonitorError("Request timed out")
        result = await coordinator._async_update_data()

        assert DEVICE_SN in result, "all entities of the device went unknown"
        points = {point["title"]: point["val"] for point in result[DEVICE_SN]["data"]}
        assert points["Battery Voltage"] == 26.4
        assert points["Data Source"] == "Local"
    finally:
        await coordinator.async_shutdown()


async def test_hybrid_retained_device_without_local_match_stays_cached(
    hass: HomeAssistant,
) -> None:
    """A retained device the local route cannot cover must not look live."""
    api = _cloud_api(_collector(), _collector(SECOND_PN))
    api.get_collector_devices.side_effect = lambda pn: {
        COLLECTOR_PN: {"dev": [_device()]},
        SECOND_PN: {"dev": [_device(SECOND_SN)]},
    }[pn]
    api.get_device_last_data.return_value = LIVE_POINTS
    api.close = AsyncMock()
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
        "hybrid-retained",
    )
    try:
        await coordinator._async_update_data()
        # The local route covers the first collector only.
        coordinator.local.async_set_updated_data(_local_payload())

        def _second_device_times_out(
            pn: str, devcode: int, devaddr: int, sn: str
        ) -> list[dict[str, Any]]:
            if sn == SECOND_SN:
                raise DessMonitorError("Request timed out")
            return LIVE_POINTS

        api.get_device_last_data.side_effect = (
            lambda pn, devcode, devaddr, sn: _second_device_times_out(
                pn, devcode, devaddr, sn
            )
        )
        result = await coordinator._async_update_data()

        sources = {
            sn: {p["title"]: p["val"] for p in payload["data"]}["Data Source"]
            for sn, payload in result.items()
        }
        assert sources == {DEVICE_SN: "Local", SECOND_SN: "Cached Cloud"}
    finally:
        await coordinator.async_shutdown()


async def test_repeated_retention_neither_grows_nor_drifts(
    cloud_coordinator: DessMonitorDataUpdateCoordinator,
) -> None:
    """Retaining the same device for many cycles must not accumulate points."""
    api = cloud_coordinator.api
    api.get_device_last_data.return_value = LIVE_POINTS
    first = await cloud_coordinator._async_update_data()
    baseline = len(first[DEVICE_SN]["data"])

    api.get_device_last_data.side_effect = DessMonitorError("Request timed out")
    for _ in range(5):
        result = await cloud_coordinator._async_update_data()

    assert len(result[DEVICE_SN]["data"]) == baseline
    points = {point["title"]: point["val"] for point in result[DEVICE_SN]["data"]}
    assert points["Battery Voltage"] == "26.1"
    assert points["Data Source"] == "Cached Cloud"


async def test_device_recovers_on_the_next_successful_cycle(
    cloud_coordinator: DessMonitorDataUpdateCoordinator,
) -> None:
    """A retained device must go live again, with no serial left marked stale."""
    api = cloud_coordinator.api
    api.get_device_last_data.return_value = LIVE_POINTS
    await cloud_coordinator._async_update_data()

    api.get_device_last_data.side_effect = DessMonitorError("Request timed out")
    await cloud_coordinator._async_update_data()
    assert cloud_coordinator.stale_cloud_serials == frozenset({DEVICE_SN})

    api.get_device_last_data.side_effect = None
    api.get_device_last_data.return_value = [
        {"title": "Battery Voltage", "val": "27.3", "unit": "V"}
    ]
    recovered = await cloud_coordinator._async_update_data()

    assert cloud_coordinator.stale_cloud_serials == frozenset()
    points = {point["title"]: point["val"] for point in recovered[DEVICE_SN]["data"]}
    assert points["Battery Voltage"] == "27.3"
    assert points["Data Source"] == "Cloud"


async def test_empty_collector_list_does_not_discard_known_devices(
    cloud_coordinator: DessMonitorDataUpdateCoordinator,
) -> None:
    """An empty collector list is treated as a failed refresh, not as removal."""
    api = cloud_coordinator.api
    api.get_device_last_data.return_value = LIVE_POINTS
    await cloud_coordinator._async_update_data()

    api.get_collectors.return_value = ([], [])
    result = await cloud_coordinator._async_update_data()

    assert DEVICE_SN in cloud_coordinator._cached_cloud_data
    points = {point["title"]: point["val"] for point in result[DEVICE_SN]["data"]}
    assert points["Data Source"] == "Cached Cloud"


async def test_first_refresh_of_an_empty_account_still_succeeds(
    hass: HomeAssistant,
) -> None:
    """Nothing cached and nothing configured is not a failure."""
    api = _cloud_api()
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300, entry_id="empty")

    assert await coordinator._async_update_data() == {}


async def test_restart_restores_a_device_whose_collector_times_out(
    hass: HomeAssistant,
) -> None:
    """Issue #54: the stored snapshot must carry a device through a cold start.

    ``async_setup_cloud_cache`` loads the previous run's snapshot before the
    first refresh, so a collector that times out during start-up no longer
    leaves its entities registered-but-unavailable.
    """
    api = _cloud_api(_collector(), _collector(SECOND_PN))
    api.get_collector_devices.side_effect = lambda pn: (
        {"dev": [_device()]}
        if pn == COLLECTOR_PN
        else _raise(DessMonitorError("Request timed out"))
    )
    api.get_device_last_data.return_value = LIVE_POINTS
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300, entry_id="restart")
    coordinator._cached_cloud_data = {
        SECOND_SN: {
            "collector": _collector(SECOND_PN),
            "device": _device(SECOND_SN),
            "data": [{"title": "Battery Voltage", "val": "25.8", "unit": "V"}],
        }
    }

    result = await coordinator._async_update_data()

    assert SECOND_SN in result, "the device stayed unavailable after a restart"
    points = {point["title"]: point["val"] for point in result[SECOND_SN]["data"]}
    assert points["Battery Voltage"] == "25.8"
    assert points["Data Source"] == "Cached Cloud"


def _raise(error: Exception) -> None:
    """Raise inside a lambda-based side effect."""
    raise error


async def test_local_push_after_a_device_timeout_reaches_entities(
    hass: HomeAssistant,
) -> None:
    """The 5s local push between cloud cycles is what the reporter actually sees.

    Pushes are built from the stored snapshot, so a device dropped from it used
    to be unreachable by local telemetry until a later cloud cycle succeeded.
    """
    api = _cloud_api(_collector())
    api.get_collector_devices.return_value = {"dev": [_device()]}
    api.get_device_last_data.return_value = LIVE_POINTS
    api.close = AsyncMock()
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
        "hybrid-push",
    )
    try:
        await coordinator._async_update_data()
        api.get_device_last_data.side_effect = DessMonitorError("Request timed out")
        await coordinator._async_update_data()

        coordinator.local.async_set_updated_data(_local_payload())
        # Let the coalescing timer fire the push the way production does.
        await asyncio.sleep(0.15)

        assert DEVICE_SN in coordinator.data
        points = {
            point["title"]: point["val"]
            for point in coordinator.data[DEVICE_SN]["data"]
        }
        assert points["Battery Voltage"] == 26.4
        assert points["Data Source"] == "Local"
    finally:
        await coordinator.async_shutdown()
