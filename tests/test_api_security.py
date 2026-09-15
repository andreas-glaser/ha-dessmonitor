"""Security regression tests for cloud transport error handling."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import aiohttp
import pytest
from yarl import URL

from custom_components.dessmonitor.api import DessMonitorAPI, DessMonitorError


async def test_transport_error_never_exposes_signed_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """aiohttp exceptions can contain their URL, including API credentials."""
    signed_url = "https://api.example.invalid/?sign=SECRET-SIGNATURE&token=SECRET-TOKEN"
    session = MagicMock()
    session.get.side_effect = aiohttp.InvalidURL(signed_url)
    api = DessMonitorAPI("user", "password", session=session)

    with caplog.at_level(logging.ERROR), pytest.raises(DessMonitorError) as raised:
        await api._fetch_json("queryDeviceLastData", signed_url)

    visible = f"{raised.value}\n{caplog.text}"
    assert "SECRET-SIGNATURE" not in visible
    assert "SECRET-TOKEN" not in visible
    assert signed_url not in visible
    assert "queryDeviceLastData" in visible


@pytest.mark.parametrize("level", [logging.ERROR, logging.DEBUG])
@pytest.mark.parametrize("error_kind", ["http", "content_type"])
async def test_authentication_error_redacts_signature_at_all_log_levels(
    caplog, level, error_kind
):
    url = URL(
        "https://api.example.invalid/public/?sign=SYNTHETIC-SIGNATURE&salt=12345678&action=auth&usr=test-user"
    )
    session = MagicMock()
    if error_kind == "http":
        session.get.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(real_url=url),
            history=(),
            status=503,
            message="Unavailable",
        )
    else:
        response = session.get.return_value.__aenter__.return_value
        response.raise_for_status = MagicMock()
        response.json.side_effect = aiohttp.ContentTypeError(
            request_info=MagicMock(real_url=url),
            history=(),
            message="Unexpected content type",
        )
    api = DessMonitorAPI("test-user", "test-password", session=session)
    with caplog.at_level(level), pytest.raises(DessMonitorError):
        await api.authenticate()
    assert "SYNTHETIC-SIGNATURE" not in caplog.text


async def test_cancelled_authentication_propagates_cancellation() -> None:
    session = MagicMock()
    session.get.side_effect = asyncio.CancelledError()
    api = DessMonitorAPI("test-user", "test-password", session=session)
    with pytest.raises(asyncio.CancelledError):
        await api.authenticate()
