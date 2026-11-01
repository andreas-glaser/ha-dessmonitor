"""Read-only PI30 identification and 17/21-field status decoding.

Some Axpert and VM IV firmwares append vendor fields after the standard 21.
Those extras are ignored rather than rejected; see issue #50.
"""

from __future__ import annotations

import re
from typing import Any

from .diagnostics import record_query
from .discovery import (
    DiscoveredInverter,
    DiscoveryError,
    DiscoveryResult,
    SendCommand,
    ascii_routes,
    device_code_candidates,
    inverter_addresses,
)
from .profile import CommandNotSupported
from .protocol import MAX_FRAME_SIZE, ProtocolError, build_pi30_poll, parse_p17_response

_STATUS_FIELDS = (
    ("Grid Voltage", 300),
    ("Grid Frequency", 70),
    ("Output Voltage", 300),
    ("Output Frequency", 70),
    ("Output Apparent Power", 150_000),
    ("Output Active Power", 150_000),
    ("Load Percent", 300),
    ("BUS Voltage", 1500),
    ("Battery Voltage", 1000),
    ("Battery Charging Current", 1000),
    ("State of Charge", 100),
    ("Inverter Heat Sink Temperature", 200),
    ("PV Charging Current", 1000),
    ("PV Voltage", 1500),
    ("Battery Voltage from SCC", 1000),
    ("Battery Discharge Current", 1000),
)
_MODES = {
    "P": "Power On",
    "S": "Standby",
    "L": "Line",
    "B": "Battery",
    "F": "Fault",
    "H": "Power Saving",
}


def _number(value: str, maximum: float) -> float:
    if re.fullmatch(r"[0-9]{1,8}(?:\.[0-9]{1,3})?", value) is None:
        raise ProtocolError("PI30 numeric field has an invalid format")
    number = float(value)
    if number > maximum:
        raise ProtocolError("PI30 numeric field is outside its supported range")
    return number


def parse_pi30_response(command: str, frame: bytes) -> dict[str, Any]:
    """Validate the envelope, checksum, protocol and supported field layout."""
    if not frame.startswith(b"(") or len(frame) > MAX_FRAME_SIZE:
        raise ProtocolError("PI30 response has an invalid envelope")
    response = parse_p17_response(frame)
    if response.response_type == "N":
        raise CommandNotSupported(command)
    if response.response_type != "D":
        raise ProtocolError("PI30 inquiry returned an acknowledgement")
    data = response.data
    if command == "QPI":
        if data != "PI30":
            raise ProtocolError(
                "unsupported inverter protocol", reason="unsupported_protocol"
            )
        return {"PI": "30"}
    if command == "QPIGS":
        fields = data.split(" ")
        # A longer reply carries vendor fields after the standard 21, which we
        # ignore. Between 18 and 20 is a truncated extended block instead, so
        # its trailing flags cannot be validated and it stays rejected.
        if len(fields) != 17 and len(fields) < 21:
            raise ProtocolError("unsupported PI30 status field count")
        values = {
            title: _number(fields[index], maximum)
            for index, (title, maximum) in enumerate(_STATUS_FIELDS)
        }
        if re.fullmatch(r"[01]{8}", fields[16]) is None:
            raise ProtocolError("invalid PI30 status flags")
        if len(fields) >= 21:
            _number(fields[17], 255)
            _number(fields[18], 255)
            values["PV Charge Power"] = _number(fields[19], 150_000)
            if re.fullmatch(r"[01]{3}", fields[20]) is None:
                raise ProtocolError("invalid PI30 extended status flags")
        # The bus and SCC battery readings have no canonical sensor here.
        values.pop("BUS Voltage")
        values.pop("Battery Voltage from SCC")
        return values
    if command == "QPIGS2":
        # Axpert MAX PI30: PV2 input current (A), voltage (V), charging power (W).
        # The tested logger appends a trailing space to this response. Vendor
        # fields after those three are ignored rather than rejected, as they
        # are for QPIGS: rejecting them would park the inquiry in its failure
        # backoff and publish no PV2 reading at all (#50).
        fields = data.split()
        if len(fields) < 3:
            raise ProtocolError("unsupported PI30 PV2 status field count")
        return {
            "PV2 Charger Current": _number(fields[0], 1000),
            "PV2 Voltage": _number(fields[1], 1500),
            "PV2 Charger Power": _number(fields[2], 150_000),
        }
    if command == "QMOD":
        if data not in _MODES:
            raise ProtocolError("unsupported PI30 operating mode")
        return {"Operating mode": _MODES[data]}
    if command == "QID":
        if re.fullmatch(r"[A-Za-z0-9]{14}", data) is None:
            raise ProtocolError("unsupported PI30 serial number format")
        return {"ID": data if data != "0" * 14 else ""}
    if command == "QVFW":
        if re.fullmatch(r"VERFW:[0-9A-F]{5}\.[0-9A-F]{2}", data) is None:
            raise ProtocolError("unsupported PI30 firmware format")
        return {"VFW": data.removeprefix("VERFW:")}
    if command == "QPIRI":
        fields = data.split(" ")
        if not 21 <= len(fields) <= 28:
            raise ProtocolError("unsupported PI30 ratings field count")
        return {
            "rated_output_power": _number(fields[6], 150_000),
            "rated_battery_voltage": _number(fields[7], 1000),
        }
    raise ProtocolError("unsupported PI30 read-only command")


async def query_pi30(
    send: SendCommand,
    device_code: int,
    collector_address: int,
    device_address: int,
    command: str,
) -> dict[str, Any]:
    """Record payload-free evidence for a single allowed inquiry."""
    payload = build_pi30_poll(command)
    with record_query(
        "pi30", command, device_code, collector_address, device_address
    ) as attempt:
        raw = await send(payload, device_code, collector_address)
        attempt.response_bytes = len(raw)
        if not raw:
            raise ProtocolError(
                "collector returned an empty inverter response", reason="empty_response"
            )
        return parse_pi30_response(command, raw)


async def discover_pi30(
    send: SendCommand,
    *,
    collector_product_number: str,
    configured_device_code: int = 0,
    reported_device_code: int = 0,
    max_address: int = 16,
    device_address: int = 0,
) -> DiscoveryResult:
    """Require both PI30 identification and usable status on the same route."""
    addresses = inverter_addresses(device_address, max_address)
    first = addresses.start
    codes = device_code_candidates(configured_device_code, reported_device_code)
    initial: dict[str, Any] = {}
    selected: tuple[int, int] | None = None
    for code, route in ascii_routes(codes, first, explicit=bool(device_address)):
        try:
            await query_pi30(send, code, route, first, "QPI")
            initial = await query_pi30(send, code, route, first, "QPIGS")
        except (TimeoutError, ProtocolError):
            continue
        selected = (code, route)
        break
    if selected is None:
        raise DiscoveryError(
            "no PI30 inverter returned valid identification and status"
        )

    code, selected_route = selected
    if selected_route == 255:
        addresses = range(first, first + 1)
    devices: list[DiscoveredInverter] = []
    seen: set[str] = set()
    for address in addresses:
        route = 255 if selected_route == 255 else address
        values = initial
        if address != first:
            try:
                await query_pi30(send, code, route, address, "QPI")
                values = await query_pi30(send, code, route, address, "QPIGS")
            except (TimeoutError, ProtocolError):
                break
        metadata: dict[str, Any] = {"PI": "30"}
        for command in ("QID", "QVFW", "QPIRI"):
            try:
                metadata.update(await query_pi30(send, code, route, address, command))
            except (TimeoutError, ProtocolError):
                continue
        serial = str(metadata.get("ID", ""))
        if serial and serial in seen:
            break
        if serial:
            seen.add(serial)
        devices.append(
            DiscoveredInverter(
                address=address,
                collector_address=route,
                serial=serial or f"{collector_product_number}-{address}",
                metadata=metadata,
                values=values,
            )
        )
        if not serial:
            break
    return DiscoveryResult(code, tuple(devices))
