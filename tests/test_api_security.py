"""Security regression tests for cloud transport error handling."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import aiohttp
import pytest

from custom_components.dessmonitor.api import DessMonitorAPI, DessMonitorError


async def test_transport_error_never_exposes_signed_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """aiohttp exceptions can contain their URL, including API credentials."""
    signed_url = (
        "https://api.example.invalid/?sign=SECRET-SIGNATURE&token=SECRET-TOKEN"
    )
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
