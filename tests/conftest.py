"""Shared fixtures for the DessMonitor test suite."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Generator
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from aiohttp.client_proto import ResponseHandler


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None, None, None]:
    """Enable loading of the custom integration in every test.

    ``enable_custom_integrations`` is provided by
    pytest-homeassistant-custom-component; without it Home Assistant refuses to
    load components under ``custom_components/``.
    """
    yield


@pytest.fixture
def mock_validate_input() -> Generator[None, None, None]:
    """Make config-flow validation succeed without any network access.

    The flow authenticates and then lists collectors; both are patched so the
    flow reaches entry creation deterministically. The HTTP session is stubbed
    too, so no real aiohttp/aiodns resolver thread is spawned (which would
    otherwise trip Home Assistant's lingering-thread cleanup check).
    """
    with (
        patch(
            "custom_components.dessmonitor.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.dessmonitor.config_flow.DessMonitorAPI.authenticate",
            return_value=True,
        ),
        patch(
            "custom_components.dessmonitor.config_flow.DessMonitorAPI.get_collectors",
            return_value=([{"pn": "PN-TEST"}], []),
        ),
    ):
        yield


@pytest.fixture
def mock_setup_entry() -> Generator[None, None, None]:
    """Stop the entry from being fully set up after the flow creates it.

    Keeps config-flow tests focused on the flow itself rather than coordinator
    start-up and live API polling.
    """
    with patch(
        "custom_components.dessmonitor.async_setup_entry",
        return_value=True,
    ):
        yield


class MemoryTransport(asyncio.Transport):
    """Replace only the socket while retaining aiohttp request serialization."""

    def __init__(self, protocol: ResponseHandler, connector: MemoryConnector) -> None:
        super().__init__()
        self.protocol = protocol
        self.connector = connector
        self.closed = False

    def is_closing(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.close()

    def write(self, data: bytes) -> None:
        self.connector.requests.append(data)
        payload = self.connector.payload
        encoded = json.dumps(payload(data) if callable(payload) else payload).encode()
        self.protocol.data_received(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(encoded)}\r\n\r\n".encode()
            + encoded
        )


class MemoryConnector(aiohttp.BaseConnector):
    """Serve per-test API responses without opening a network connection."""

    def __init__(self) -> None:
        super().__init__(force_close=True)
        self.requests: list[bytes] = []
        self.payload: dict[str, Any] | Callable[[bytes], dict[str, Any]] = {
            "err": 0,
            "dat": {"token": "test-token", "secret": "test-secret", "expire": 3600},
        }

    async def _create_connection(self, req, traces, timeout) -> ResponseHandler:
        protocol = ResponseHandler(asyncio.get_running_loop())
        protocol.connection_made(MemoryTransport(protocol, self))
        return protocol


@pytest.fixture
async def cloud_transport() -> (
    AsyncIterator[tuple[aiohttp.ClientSession, MemoryConnector]]
):
    connector = MemoryConnector()
    async with aiohttp.ClientSession(connector=connector) as session:
        yield session, connector
