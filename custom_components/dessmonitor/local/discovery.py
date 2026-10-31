"""Reusable, read-only local inverter discovery.

Both Home Assistant and the contributor CLI use this module so device-code
probing, address de-duplication, and response validation cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .diagnostics import record_query
from .profile import parse_command_response
from .protocol import ProtocolError, build_p17_poll

SendCommand = Callable[[bytes, int, int], Awaitable[bytes]]

# These are Eybond *tunnel* codes observed for PI18/P17. They are not the
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
    collector_address: int
    values: dict[str, Any] = field(default_factory=dict)


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


def inverter_addresses(device_address: int, max_address: int) -> range:
    """Preserve the legacy scan unless one explicit inverter is selected."""
    if type(device_address) is not int or not 0 <= device_address <= 247:
        raise DiscoveryError("inverter address must be between 0 (automatic) and 247")
    if type(max_address) is not int or not 1 <= max_address <= 255:
        raise DiscoveryError("maximum device address must be between 1 and 255")
    if device_address:
        return range(device_address, device_address + 1)
    return range(1, max_address + 1)


def ascii_routes(
    codes: tuple[int, ...], address: int, *, explicit: bool = False
) -> tuple[tuple[int, int], ...]:
    """Try all direct routes before the collector's unaddressed UART fallback."""
    targets = (address,) if explicit else tuple(dict.fromkeys((address, 255)))
    return tuple((code, target) for target in targets for code in codes)


async def query_p17(
    send: SendCommand,
    device_code: int,
    device_address: int,
    command: str,
    *,
    protocol_id: str = "17",
    collector_address: int | None = None,
) -> dict[str, Any]:
    """Send and parse one read-only P17 query."""
    route = device_address if collector_address is None else collector_address
    with record_query("p17", command, device_code, route, device_address) as attempt:
        raw = await send(
            build_p17_poll(command, escape_crc=protocol_id != "18"),
            device_code,
            route,
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
    device_address: int = 0,
) -> DiscoveryResult:
    """Discover P17 device code and unique, contiguous inverter addresses."""
    addresses = inverter_addresses(device_address, max_address)
    first_address = addresses.start

    selected_code: int | None = None
    selected_route = first_address
    codes = device_code_candidates(configured_device_code, reported_device_code)
    for device_code, collector_address in ascii_routes(
        codes, first_address, explicit=bool(device_address)
    ):
        try:
            await query_p17(
                send,
                device_code,
                first_address,
                "PI",
                collector_address=collector_address,
            )
        except (TimeoutError, ProtocolError):
            continue
        selected_code = device_code
        selected_route = collector_address
        break
    if selected_code is None:
        raise DiscoveryError(
            "no P17-compatible inverter was identified; inspect local probe diagnostics"
        )

    discovered: list[DiscoveredInverter] = []
    seen_serials: set[str] = set()
    if selected_route == 255:
        addresses = range(first_address, first_address + 1)
    for address in addresses:
        route = 255 if selected_route == 255 else address
        try:
            protocol = await query_p17(
                send, selected_code, address, "PI", collector_address=route
            )
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
                        send,
                        selected_code,
                        address,
                        command,
                        protocol_id=protocol_id,
                        collector_address=route,
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
                collector_address=route,
            )
        )
        # Without a stable serial, a collector that ignores the requested
        # address could manufacture identical phantom devices indefinitely.
        if not serial:
            break

    if not discovered:
        raise DiscoveryError("a protocol responded but no inverter address was found")
    return DiscoveryResult(selected_code, tuple(discovered))
