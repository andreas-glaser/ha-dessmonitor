"""Shared private-LAN validation for local collector communication."""

from __future__ import annotations

import ipaddress

LOCAL_IPV4_NETWORKS: tuple[ipaddress.IPv4Network, ...] = tuple(
    ipaddress.IPv4Network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
)


def normalize_local_ipv4(value: str) -> str:
    """Return a normalized RFC1918 or loopback IPv4 address."""
    address = ipaddress.ip_address(value.strip())
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network for network in LOCAL_IPV4_NETWORKS
    ):
        raise ValueError("address must be an RFC1918 or loopback IPv4 address")
    return str(address)


def is_local_ipv4_network(network: ipaddress.IPv4Network) -> bool:
    """Return whether every address in a network is in the allowed LAN ranges."""
    return any(network.subnet_of(candidate) for candidate in LOCAL_IPV4_NETWORKS)
