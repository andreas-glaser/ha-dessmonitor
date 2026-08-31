"""Integration mode contract tests for API, local-only, and hybrid setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from custom_components.dessmonitor import (
    DessMonitorDataUpdateCoordinator,
    LOCAL_PLATFORMS,
    PLATFORMS,
    async_reload_entry,
    async_setup_entry,
)
from custom_components.dessmonitor.const import (
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_MODE,
    CONNECTION_TYPE_LOCAL,
    DOMAIN,
    LOCAL_MODE_PREFER_LOCAL,
)
from homeassistant.helpers.update_coordinator import UpdateFailed


def _entry(*, data: dict | None = None, options: dict | None = None) -> MagicMock:
    """Create the small ConfigEntry surface used during setup."""
    entry = MagicMock()
    entry.entry_id = "mode-entry"
    entry.data = data or {"username": "existing", "password": "stored"}
    entry.options = options or {}
    entry.add_update_listener.return_value = MagicMock()
    return entry


async def test_legacy_entry_remains_api_mode_without_reconfiguration(
    hass: HomeAssistant,
) -> None:
    """Entries predating connection_type keep their identity and API path."""
    entry = _entry()
    api = MagicMock()
    coordinator = MagicMock()
    coordinator.async_shutdown = AsyncMock()

    with (
        patch(
            "custom_components.dessmonitor._create_api_client", return_value=api
        ) as create_api,
        patch(
            "custom_components.dessmonitor._authenticate_api_client",
            new=AsyncMock(),
        ) as authenticate,
        patch(
            "custom_components.dessmonitor._create_coordinator",
            new=AsyncMock(return_value=coordinator),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry)

    create_api.assert_called_once_with(hass, entry)
    authenticate.assert_awaited_once_with(api)
    forward.assert_awaited_once_with(entry, PLATFORMS)
    assert hass.data[DOMAIN][entry.entry_id] is coordinator
    assert CONF_CONNECTION_TYPE not in entry.data


async def test_existing_api_entry_can_enable_hybrid_in_place(
    hass: HomeAssistant,
) -> None:
    """Preferred local is an option on the same API entry, not a new entry."""
    entry = _entry(options={CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL})
    api = MagicMock()
    coordinator = MagicMock()

    with (
        patch(
            "custom_components.dessmonitor._create_api_client", return_value=api
        ),
        patch(
            "custom_components.dessmonitor._authenticate_api_client",
            new=AsyncMock(),
        ) as authenticate,
        patch(
            "custom_components.dessmonitor._create_coordinator",
            new=AsyncMock(return_value=coordinator),
        ) as create_coordinator,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry)

    authenticate.assert_not_awaited()
    create_coordinator.assert_awaited_once_with(hass, entry, api)
    forward.assert_awaited_once_with(entry, PLATFORMS)
    assert hass.data[DOMAIN][entry.entry_id] is coordinator


async def test_local_only_skips_api_and_write_platforms(
    hass: HomeAssistant,
) -> None:
    """Local-only never requires credentials or loads control entities."""
    entry = _entry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL})

    with (
        patch(
            "custom_components.dessmonitor._async_setup_local_entry",
            new=AsyncMock(return_value=True),
        ) as setup_local,
        patch(
            "custom_components.dessmonitor._create_api_client"
        ) as create_api,
    ):
        assert await async_setup_entry(hass, entry)

    setup_local.assert_awaited_once_with(hass, entry)
    create_api.assert_not_called()
    assert LOCAL_PLATFORMS == [Platform.SENSOR, Platform.BINARY_SENSOR]
    assert all(
        platform not in LOCAL_PLATFORMS
        for platform in (Platform.BUTTON, Platform.NUMBER, Platform.SELECT)
    )


async def test_api_only_retains_explicit_cached_snapshot_on_outage(
    hass: HomeAssistant,
) -> None:
    """The primary API mode keeps its last snapshot through a transient outage."""
    api = MagicMock(close=AsyncMock())
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    coordinator._cached_cloud_data = {
        "API-SERIAL": {
            "collector": {"pn": "COLLECTOR"},
            "device": {"sn": "API-SERIAL"},
            "data": [{"title": "Grid Voltage", "val": 230, "unit": "V"}],
        }
    }
    coordinator._fetch_collectors = AsyncMock(
        side_effect=UpdateFailed("API unavailable")
    )

    result = await coordinator._async_update_data()
    points = {
        point["title"]: point["val"] for point in result["API-SERIAL"]["data"]
    }
    assert points["Grid Voltage"] == 230
    assert points["Data Source"] == "Cached Cloud"


async def test_reload_uses_home_assistant_entry_lifecycle(
    hass: HomeAssistant,
) -> None:
    """Option changes must unload callbacks and old coordinator timers."""
    entry = _entry()
    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as reload_entry:
        await async_reload_entry(hass, entry)
    reload_entry.assert_awaited_once_with(entry.entry_id)
