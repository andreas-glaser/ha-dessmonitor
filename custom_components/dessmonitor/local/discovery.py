"""Reusable, read-only local inverter discovery.

Both Home Assistant and the contributor CLI use this module so device-code
probing, address de-duplication, and response validation cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .diagnostics import record_query
from .profile import parse_command_response
from .protocol import ProtocolError, build_p17_poll

SendCommand = Callable[[bytes, int, int], Awaitable[bytes]]

# These are EyeBond *tunnel* codes observed for PI18/P17. They are not the
# cloud API's device-family codes, which describe a different layer and must
# not be sprayed onto the local bus as guesses.
KNOWN_DEVICE_CODES = (2452, 258)
STARTUP_COMMANDS = ("ID", "GMN", "VFW", "PIRI")


class DiscoveryError(ProtocolError):
    """Raised when no supported local inverter can be discovered."""


@dataclass(frozen=True, slots=True)
class DiscoveredInverter:
    """Read-only metadata for one unique inverter address."""

    address: int
    serial: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Successful transport-code and inverter-address discovery."""

    device_code: int
    inverters: tuple[DiscoveredInverter, ...]


def device_code_candidates(configured: int, reported: int) -> tuple[int, ...]:
    """Return a stable, de-duplicated probe order."""
    if configured:
        if not 0 < configured <= 0xFFFF:
            raise DiscoveryError("configured device code is outside the 16-bit range")
        return (configured,)
    candidates = (reported, *KNOWN_DEVICE_CODES)
    return tuple(dict.fromkeys(code for code in candidates if 0 < code <= 0xFFFF))


async def query_p17(
    send: SendCommand,
    device_code: int,
    device_address: int,
    command: str,
    *,
    protocol_id: str = "17",
) -> dict[str, Any]:
    """Send and parse one read-only P17 query."""
    with record_query(
        "p17", command, device_code, device_address, device_address
    ) as attempt:
        raw = await send(
            build_p17_poll(command, escape_crc=protocol_id != "18"),
            device_code,
            device_address,
        )
        attempt.response_bytes = len(raw)
        if not raw:
            raise ProtocolError(
                "collector returned an empty inverter response", reason="empty_response"
            )
        return parse_command_response(command, raw, protocol_id=protocol_id)


async def discover_p17(
    send: SendCommand,
    *,
    collector_product_number: str,
    configured_device_code: int = 0,
    reported_device_code: int = 0,
    max_address: int = 16,
) -> DiscoveryResult:
    """Discover P17 device code and unique, contiguous inverter addresses."""
    if not 1 <= max_address <= 255:
        raise DiscoveryError("maximum device address must be between 1 and 255")

    selected_code: int | None = None
    for device_code in device_code_candidates(
        configured_device_code, reported_device_code
    ):
        try:
            await query_p17(send, device_code, 1, "PI")
        except (TimeoutError, ProtocolError):
            continue
        selected_code = device_code
        break
    if selected_code is None:
        raise DiscoveryError(
            "no P17-compatible inverter was identified; inspect local probe diagnostics"
        )

    discovered: list[DiscoveredInverter] = []
    seen_serials: set[str] = set()
    for address in range(1, max_address + 1):
        try:
            protocol = await query_p17(send, selected_code, address, "PI")
        except (TimeoutError, ProtocolError):
            break

        protocol_id = protocol["PI"]
        metadata: dict[str, Any] = dict(protocol)
        for command in STARTUP_COMMANDS:
            if protocol_id == "18" and command == "GMN":
                continue
            try:
                metadata.update(
                    await query_p17(
                        send, selected_code, address, command, protocol_id=protocol_id
                    )
                )
            except (TimeoutError, ProtocolError):
                continue

        serial = str(metadata.get("ID", "")).strip()
        if serial and serial in seen_serials:
            break
        if serial:
            seen_serials.add(serial)
        discovered.append(
            DiscoveredInverter(
                address=address,
                serial=serial or f"{collector_product_number}-{address}",
                metadata=metadata,
            )
        )
        # Without a stable serial, a collector that ignores the requested
        # address could manufacture identical phantom devices indefinitely.
        if not serial:
            break

    if not discovered:
        raise DiscoveryError("a protocol responded but no inverter address was found")
    return DiscoveryResult(selected_code, tuple(discovered))
