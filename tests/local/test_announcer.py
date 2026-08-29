"""Tests for targeted collector callback requests."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dessmonitor.local.announcer import CollectorAnnouncer


async def test_announcer_warns_once_when_callback_never_arrives(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A blocked callback produces one actionable firewall warning."""
    announcer = CollectorAnnouncer(
        server_ip="192.168.2.9",
        server_port=8899,
        collector_ip="192.168.10.100",
        collector_udp_port=58899,
        warning_after=60,
    )
    loop = MagicMock()
    loop.time.side_effect = [0.0, 30.0, 61.0]

    with (
        caplog.at_level(logging.WARNING),
        patch(
            "custom_components.dessmonitor.local.announcer.asyncio.get_running_loop",
            return_value=loop,
        ),
        patch.object(
            announcer,
            "_send_once",
            new=AsyncMock(side_effect=[None, None, asyncio.CancelledError()]),
        ),
        patch(
            "custom_components.dessmonitor.local.announcer.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await announcer._run()

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert "No callback from local collector 192.168.10.100" in messages[0]
    assert "outbound UDP port 58899" in messages[0]
    assert "inbound TCP access" in messages[0]
    assert "192.168.2.9:8899" in messages[0]
