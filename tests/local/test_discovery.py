"""Tests for reusable read-only P17 discovery."""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.local.discovery import (
    DiscoveryError,
    device_code_candidates,
    discover_p17,
)
from custom_components.dessmonitor.local.protocol import build_p17_response


def _command(payload: bytes) -> str:
    """Extract the ASCII command from a test request."""
    return payload[5:-3].decode("ascii")


def test_manual_device_code_skips_probe_list() -> None:
    """A configured code produces one deterministic candidate."""
    assert device_code_candidates(0x1234, 0x0994) == (0x1234,)


def test_reported_device_code_is_preferred_and_deduplicated() -> None:
    """Heartbeat metadata is tried first without probing a code twice."""
    candidates = device_code_candidates(0, 2452)
    assert candidates[0] == 2452
    assert candidates.count(2452) == 1


async def test_discovery_probes_code_and_deduplicates_echoed_addresses() -> None:
    """Wrong transport codes fail safely and echoed serials stop bus scanning."""
    calls: list[tuple[int, int, str]] = []

    async def send(payload: bytes, device_code: int, address: int) -> bytes:
        command = _command(payload)
        calls.append((device_code, address, command))
        if device_code != 2452:
            return b""
        responses = {
            "PI": "17",
            "ID": "08ABCD12340000",
            "GMN": "04TEST0000",
            "VFW": "031.0000",
            "PIRI": "2300,100,2300,500,100,5000,4500,480,440,420,460,560,540,2",
        }
        return build_p17_response("D", responses[command])

    result = await discover_p17(
        send,
        collector_product_number="COLLECTOR",
        reported_device_code=999,
    )

    assert result.device_code == 2452
    assert len(result.inverters) == 1
    assert result.inverters[0].serial == "ABCD1234"
    assert result.inverters[0].metadata["GMN"] == "TEST"
    assert calls[0][:2] == (999, 1)


async def test_discovery_uses_stable_fallback_identity() -> None:
    """A missing ID does not make entity identity depend on mutable metadata."""

    async def send(payload: bytes, _device_code: int, address: int) -> bytes:
        command = _command(payload)
        if address > 1:
            raise TimeoutError
        if command == "PI":
            return build_p17_response("D", "17")
        return build_p17_response("N")

    result = await discover_p17(
        send,
        collector_product_number="COLLECTOR",
        configured_device_code=2452,
    )

    assert result.inverters[0].serial == "COLLECTOR-1"


async def test_discovery_fails_when_no_profile_responds() -> None:
    """Empty and invalid responses cannot create phantom devices."""

    async def send(_payload: bytes, _device_code: int, _address: int) -> bytes:
        return b""

    with pytest.raises(DiscoveryError, match="no P17-compatible"):
        await discover_p17(send, collector_product_number="COLLECTOR")
