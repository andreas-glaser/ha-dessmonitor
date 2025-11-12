"""Home Assistant specific fixtures for the DessMonitor integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor.const import (
    CONF_COMPANY_KEY,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    DEFAULT_COMPANY_KEY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)


@dataclass
class MockDessMonitorAPI:
    """Deterministic fake API used by HA integration tests."""

    payload: dict[str, Any]

    async def _make_request(self, action: str, params: dict[str, Any] | None = None):
        """Return minimal payloads for API calls invoked during coordinator refresh."""
        if action == "queryPlants":
            return {"dat": {"plant": [{"pid": "test-project"}]}}
        return {}

    async def load_saved_token(self) -> bool:
        return True

    async def authenticate(self) -> None:
        return None

    async def clear_saved_token(self) -> None:
        return None

    async def get_collectors(self):
        return self.payload["collectors"], []

    async def get_collector_devices(self, pn: str) -> dict[str, Any]:
        return {"dev": self.payload["devices"].get(pn, [])}

    async def get_device_last_data(
        self, pn: str, devcode: int, devaddr: int, sn: str
    ) -> list[dict[str, Any]]:
        return self.payload["device_data"].get(sn, [])

    async def get_device_summary_data(self, project_id: str | int):
        return self.payload.get("summary", {})

    async def close(self) -> None:
        return None


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a default config entry for the integration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_COMPANY_KEY: DEFAULT_COMPANY_KEY,
        },
        options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
        title="DessMonitor",
    )
    return entry


@pytest.fixture
def patch_api(monkeypatch, json_fixture_loader) -> Callable[[], MockDessMonitorAPI]:
    """Patch the API factory to return our deterministic mock."""
    payload = json_fixture_loader("devcode_2376_realtime.json")

    def _factory(*args, **kwargs):
        return MockDessMonitorAPI(payload)

    monkeypatch.setattr(
        "custom_components.dessmonitor._create_api_client",
        lambda hass, entry: _factory(),
    )

    return lambda: MockDessMonitorAPI(payload)
