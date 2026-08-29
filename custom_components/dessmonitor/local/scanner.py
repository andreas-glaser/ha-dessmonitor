"""Bounded LAN discovery for EyeBond callback-capable collectors."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass

from .network import is_local_ipv4_network, normalize_local_ipv4

_REPLY_PATTERN = re.compile(rb"^rsp>server=([12]);(?:\r?\n)?$")
_MAX_SCAN_ADDRESSES = 256


class ScanError(ValueError):
    """Raised when a requested network scan is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class CollectorProbe:
    """Strictly validated UDP reply from one collector candidate."""

    ip: str
    reply_code: int


def scan_network_for_host(
    host: str, network: str | None = None
) -> ipaddress.IPv4Network:
    """Return an explicit network or the host's bounded local /24."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as err:
        raise ScanError("scan host must be an IPv4 address") from err
    if not isinstance(address, ipaddress.IPv4Address):
        raise ScanError("scan host must be an IPv4 address")
    try:
        normalize_local_ipv4(host)
    except ValueError as err:
        raise ScanError("scan host must be an RFC1918 or loopback address") from err

    try:
        result = (
            ipaddress.ip_network(network, strict=False)
            if network
            else ipaddress.ip_network(f"{address}/24", strict=False)
        )
    except ValueError as err:
        raise ScanError("scan network is invalid") from err
    if not isinstance(result, ipaddress.IPv4Network):
        raise ScanError("scan network must use IPv4")
    if address not in result:
        raise ScanError("scan host is not inside the requested network")
    if result.num_addresses > _MAX_SCAN_ADDRESSES:
        raise ScanError("scan network is larger than the allowed /24 boundary")
    if not is_local_ipv4_network(result):
        raise ScanError("scan network is not an RFC1918 or loopback LAN")
    return result


def build_callback_messages(server_ip: str, server_port: int) -> tuple[bytes, ...]:
    """Return the three callback payload variants used by collector firmware."""
    try:
        address = ipaddress.ip_address(server_ip)
    except ValueError as err:
        raise ScanError("callback server must be an IPv4 address") from err
    if not isinstance(address, ipaddress.IPv4Address):
        raise ScanError("callback server must be an IPv4 address")
    try:
        normalize_local_ipv4(server_ip)
    except ValueError as err:
        raise ScanError(
            "callback server must be an RFC1918 or loopback address"
        ) from err
    if not 1 <= server_port <= 65535:
        raise ScanError("callback server port is outside the valid range")
    base = f"set>server={address}:{server_port};".encode("ascii")
    return base, base + b"\r\n", base + b"\n"


async def scan_collectors(
    *,
    bind_ip: str,
    advertised_server_ip: str,
    advertised_server_port: int,
    udp_port: int = 58899,
    network: str | None = None,
    timeout: float = 1.5,
) -> tuple[CollectorProbe, ...]:
    """Broadcast, then use one bounded /24 unicast fallback for UDP replies."""
    scan_network = scan_network_for_host(bind_ip, network)
    if not 1 <= udp_port <= 65535:
        raise ScanError("collector UDP port is outside the valid range")
    if not 0.1 <= timeout <= 10:
        raise ScanError("scan timeout must be between 0.1 and 10 seconds")
    messages = build_callback_messages(advertised_server_ip, advertised_server_port)

    loop = asyncio.get_running_loop()
    replies: dict[str, CollectorProbe] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((bind_ip, 0))

        # One broadcast trigger is the normal fast path.
        await loop.sock_sendto(
            sock, messages[0], (str(scan_network.broadcast_address), udp_port)
        )
        await _collect_replies(sock, scan_network, replies, timeout)

        # Some APs suppress broadcast replies. Probe only this bounded /24,
        # excluding the HA host, and send one small datagram per address.
        if not replies:
            bind_address = ipaddress.ip_address(bind_ip)
            for target in scan_network.hosts():
                if target == bind_address:
                    continue
                await loop.sock_sendto(sock, messages[0], (str(target), udp_port))
            await _collect_replies(sock, scan_network, replies, timeout)

        # Old firmware variants require a line terminator. Only retry the two
        # compact variants when the base payload found nothing.
        if not replies:
            for message in messages[1:]:
                await loop.sock_sendto(
                    sock,
                    message,
                    (str(scan_network.broadcast_address), udp_port),
                )
            await _collect_replies(sock, scan_network, replies, timeout)

    return tuple(replies[ip] for ip in sorted(replies, key=ipaddress.ip_address))


async def _collect_replies(
    sock: socket.socket,
    network: ipaddress.IPv4Network,
    replies: dict[str, CollectorProbe],
    timeout: float,
) -> None:
    """Collect strict replies until a single monotonic deadline."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return
        try:
            payload, peer = await asyncio.wait_for(
                loop.sock_recvfrom(sock, 512), timeout=remaining
            )
        except TimeoutError:
            return
        try:
            peer_address = ipaddress.ip_address(peer[0])
        except ValueError:
            continue
        match = _REPLY_PATTERN.fullmatch(payload)
        if (
            not isinstance(peer_address, ipaddress.IPv4Address)
            or peer_address not in network
            or match is None
        ):
            continue
        replies[str(peer_address)] = CollectorProbe(
            ip=str(peer_address), reply_code=int(match.group(1))
        )
