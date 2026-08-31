"""Tests for bounded, strict collector LAN discovery."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.dessmonitor.local.scanner import (
    ScanError,
    build_callback_messages,
    scan_collectors,
    scan_network_for_host,
)

pytestmark = pytest.mark.usefixtures("socket_enabled")


class _FakeCollector(asyncio.DatagramProtocol):
    """Reply to a valid callback request, after one malformed datagram."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.requests: list[bytes] = []

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        self.requests.append(data)
        assert self.transport is not None
        self.transport.sendto(b"not-an-eybond-reply", addr)
        self.transport.sendto(b"rsp>server=1;\r\n", addr)


def test_scan_network_is_bounded_and_contains_host() -> None:
    """Default discovery cannot expand beyond the local /24."""
    assert str(scan_network_for_host("192.168.50.20")) == "192.168.50.0/24"
    assert str(
        scan_network_for_host("192.168.50.20", "192.168.50.0/26")
    ) == "192.168.50.0/26"
    with pytest.raises(ScanError, match="larger"):
        scan_network_for_host("192.168.50.20", "192.168.50.0/23")
    with pytest.raises(ScanError, match="not inside"):
        scan_network_for_host("192.168.50.20", "192.168.51.0/24")
    with pytest.raises(ScanError, match="RFC1918"):
        scan_network_for_host("203.0.113.5")


def test_callback_message_variants_are_small_and_explicit() -> None:
    """Compatibility variants advertise only the configured listener."""
    messages = build_callback_messages("192.168.50.20", 8899)
    assert messages == (
        b"set>server=192.168.50.20:8899;",
        b"set>server=192.168.50.20:8899;\r\n",
        b"set>server=192.168.50.20:8899;\n",
    )


async def test_scan_falls_back_to_bounded_unicast_and_validates_reply() -> None:
    """A suppressed broadcast still finds a strict reply on one tiny subnet."""
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _FakeCollector,
        local_addr=("127.0.0.2", 0),
    )
    port = int(transport.get_extra_info("sockname")[1])
    try:
        results = await scan_collectors(
            bind_ip="127.0.0.1",
            advertised_server_ip="127.0.0.1",
            advertised_server_port=8899,
            udp_port=port,
            network="127.0.0.0/30",
            timeout=0.1,
        )
    finally:
        transport.close()

    assert [(result.ip, result.reply_code) for result in results] == [
        ("127.0.0.2", 1)
    ]
    assert protocol.requests
