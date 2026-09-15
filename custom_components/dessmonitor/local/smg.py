"""Read-only SMG-family Modbus driver over the EyeBond tunnel.

The register blocks and scaling follow the published ``Modbus_RTU RS232
communication protocol, Version 1.0 (Nov 2021)``.  This module deliberately
contains no Modbus write functions or writable register descriptions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .diagnostics import record_query
from .modbus import (
    ModbusError,
    build_read_holding_request,
    parse_read_holding_response,
    to_signed_16,
)
from .protocol import ProtocolError

SendCommand = Callable[[bytes, int, int], Awaitable[bytes]]

SMG_PROTOCOL = "smg_modbus"
SMG_CLOUD_DEVICE_CODE = 2376
SMG_TUNNEL_DEVICE_CODE = 1
SMG_TUNNEL_COLLECTOR_ADDRESS = 0xFF
# Observed EyeBond heartbeat codes for collectors tunnelling the standard SMG
# Modbus protocol. They are routing hints only; strict function-03 response
# validation is still required before the driver is selected.
SMG_REPORTED_COLLECTOR_CODES = (1, 258)

_SERIAL_START = 186
_SERIAL_COUNT = 12
_LIVE_START = 201
_LIVE_COUNT = 34

_OPERATING_MODES = {
    0: "Power On",
    1: "Standby",
    2: "Mains",
    3: "Off-Grid Mode",
    4: "Bypass",
    5: "Charging",
    6: "Fault",
}


@dataclass(frozen=True, slots=True)
class SmgRoute:
    """Exact EyeBond tunnel and Modbus slave route."""

    device_code: int
    collector_address: int
    slave_address: int


@dataclass(frozen=True, slots=True)
class SmgDevice:
    """Read-only SMG device discovered behind a collector."""

    route: SmgRoute
    serial: str
    model: str
    firmware: str
    metadata: dict[str, Any]
    initial_values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Field:
    register: int
    title: str
    divisor: int = 1
    signed: bool = False
    minimum: float | None = None
    maximum: float | None = None


# Canonical titles intentionally reuse this integration's existing entity keys,
# preserving entity unique IDs and recorder history in hybrid mode.
_LIVE_FIELDS = (
    _Field(202, "Grid Voltage", 10, minimum=0, maximum=300),
    _Field(203, "Grid Frequency", 100, minimum=0, maximum=70),
    _Field(204, "Grid Power", signed=True, minimum=-100_000, maximum=100_000),
    _Field(205, "Inverter Voltage", 10, minimum=0, maximum=300),
    _Field(206, "Inverter Current", 10, signed=True, minimum=-1000, maximum=1000),
    _Field(207, "Inverter frequency", 100, minimum=0, maximum=70),
    _Field(209, "AC charging power", signed=True, minimum=-100_000, maximum=100_000),
    _Field(210, "Output Voltage", 10, minimum=0, maximum=300),
    _Field(211, "Output Current", 10, signed=True, minimum=-1000, maximum=1000),
    _Field(212, "Output Frequency", 100, minimum=0, maximum=70),
    _Field(213, "Output Active Power", signed=True, minimum=-100_000, maximum=100_000),
    _Field(214, "Output Apparent Power", minimum=0, maximum=150_000),
    _Field(215, "Battery Voltage", 10, minimum=0, maximum=1000),
    _Field(217, "Battery Power", signed=True, minimum=-100_000, maximum=100_000),
    _Field(219, "PV Voltage", 10, minimum=0, maximum=1500),
    _Field(220, "PV Current", 10, signed=True, minimum=-1000, maximum=1000),
    _Field(223, "PV Power", signed=True, minimum=-100_000, maximum=100_000),
    _Field(224, "PV Charge Power", signed=True, minimum=-100_000, maximum=100_000),
    _Field(225, "Load Percent", minimum=0, maximum=300),
    _Field(226, "DC Module Termperature", signed=True, minimum=-60, maximum=250),
    _Field(227, "INV Module Termperature", signed=True, minimum=-60, maximum=250),
    _Field(229, "State of Charge", minimum=0, maximum=100),
    _Field(232, "Battery Current", 10, signed=True, minimum=-1000, maximum=1000),
    _Field(
        233, "Battery Charging Current", 10, signed=True, minimum=-1000, maximum=1000
    ),
    _Field(234, "PV charging current", 10, signed=True, minimum=-1000, maximum=1000),
)


async def read_holding_registers(
    send: SendCommand,
    route: SmgRoute,
    start_register: int,
    register_count: int,
) -> tuple[int, ...]:
    """Read and strictly validate one complete SMG register block."""
    request = build_read_holding_request(
        route.slave_address, start_register, register_count
    )
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with record_query(
                SMG_PROTOCOL,
                "read_holding_registers",
                route.device_code,
                route.collector_address,
                route.slave_address,
            ) as query:
                query.details = {
                    "start_register": start_register,
                    "register_count": register_count,
                }
                response = await send(
                    request, route.device_code, route.collector_address
                )
                query.response_bytes = len(response)
                if not response:
                    raise ModbusError(
                        "collector returned an empty Modbus response",
                        reason="empty_response",
                    )
                return parse_read_holding_response(
                    response,
                    slave_address=route.slave_address,
                    register_count=register_count,
                )
        except (TimeoutError, ModbusError) as err:
            last_error = err
            if attempt == 0:
                await asyncio.sleep(0.15)
    raise ModbusError(str(last_error or "SMG register read failed"))


def decode_live_registers(registers: tuple[int, ...]) -> dict[str, Any]:
    """Decode a complete, plausible SMG live register block."""
    if len(registers) != _LIVE_COUNT:
        raise ModbusError(
            f"SMG live block has {len(registers)} registers (expected {_LIVE_COUNT})"
        )
    if all(value in (0, 0xFFFF) for value in registers):
        raise ModbusError("SMG live block contains no usable data")

    mode_raw = registers[201 - _LIVE_START]
    if mode_raw not in _OPERATING_MODES:
        raise ModbusError(f"SMG operating mode {mode_raw} is not plausible")
    values: dict[str, Any] = {"Operating mode": _OPERATING_MODES[mode_raw]}

    for field in _LIVE_FIELDS:
        raw = registers[field.register - _LIVE_START]
        if not field.signed and raw == 0xFFFF:
            continue
        numeric = to_signed_16(raw) if field.signed else raw
        value: float | int
        if field.divisor == 1:
            value = numeric
        else:
            value = round(numeric / field.divisor, len(str(field.divisor)) - 1)
        if field.minimum is not None and value < field.minimum:
            continue
        if field.maximum is not None and value > field.maximum:
            continue
        if field.title == "Output Active Power":
            value = max(0, value)
        values[field.title] = value

    if not any(
        title in values
        for title in ("Output Voltage", "Battery Voltage", "PV Voltage", "Grid Voltage")
    ):
        raise ModbusError("SMG live block failed voltage plausibility checks")
    return values


async def discover_smg(
    send: SendCommand,
    *,
    collector_product_number: str,
    configured_device_code: int = 0,
    reported_device_code: int = 0,
    max_address: int = 16,
) -> tuple[SmgDevice, ...]:
    """Discover one or more SMG Modbus slaves using read-only requests."""
    if not 1 <= max_address <= 247:
        raise ModbusError("maximum SMG slave address must be between 1 and 247")

    tunnel_codes = _tunnel_device_codes(configured_device_code, reported_device_code)
    selected: tuple[int, int] | None = None
    first_live: tuple[int, ...] | None = None
    for device_code in tunnel_codes:
        for collector_address in (SMG_TUNNEL_COLLECTOR_ADDRESS, 1):
            route = SmgRoute(device_code, collector_address, 1)
            try:
                candidate = await read_holding_registers(
                    send, route, _LIVE_START, _LIVE_COUNT
                )
                decode_live_registers(candidate)
            except (TimeoutError, ProtocolError):
                continue
            selected = (device_code, collector_address)
            first_live = candidate
            break
        if selected is not None:
            break
    if selected is None or first_live is None:
        raise ModbusError("no SMG/Modbus inverter responded")

    devices: list[SmgDevice] = []
    seen_serials: set[str] = set()
    for slave_address in range(1, max_address + 1):
        route = SmgRoute(selected[0], selected[1], slave_address)
        try:
            live_registers = (
                first_live
                if slave_address == 1
                else await read_holding_registers(send, route, _LIVE_START, _LIVE_COUNT)
            )
            live_values = decode_live_registers(live_registers)
        except (TimeoutError, ProtocolError):
            if devices:
                break
            continue

        serial = await _read_serial(send, route)
        if serial and serial in seen_serials:
            break
        if serial:
            seen_serials.add(serial)
        metadata = await _read_identity_metadata(send, route)
        rated_power = metadata.get("rated_power")
        model_code = metadata.get("model_code")
        model_parts = ["SMG / Modbus"]
        if model_code not in (None, 0, 0xFFFF):
            model_parts.append(f"model {model_code}")
        if isinstance(rated_power, int) and 100 <= rated_power <= 100_000:
            model_parts.append(f"{rated_power}W")
        devices.append(
            SmgDevice(
                route=route,
                serial=serial or f"{collector_product_number}-{slave_address}",
                model=(
                    " (".join((model_parts[0], ", ".join(model_parts[1:]) + ")"))
                    if len(model_parts) > 1
                    else model_parts[0]
                ),
                firmware="",
                metadata=metadata,
                initial_values=live_values,
            )
        )
        # Do not create phantom devices if firmware ignores the Modbus slave
        # field and does not expose a serial that can prove uniqueness.
        if not serial:
            break
    if not devices:
        raise ModbusError("SMG tunnel responded but no plausible inverter was found")
    return tuple(devices)


async def poll_smg(
    send: SendCommand, route: SmgRoute, *, include_status: bool = False
) -> dict[str, Any]:
    """Poll the live block and, less often, the two read-only status blocks."""
    live = await read_holding_registers(send, route, _LIVE_START, _LIVE_COUNT)
    values = decode_live_registers(live)
    if not include_status:
        return values

    for start, title in ((100, "Fault Code"), (108, "Warning Code")):
        try:
            words = await read_holding_registers(send, route, start, 2)
        except (TimeoutError, ProtocolError):
            continue
        values[title] = (words[0] << 16) | words[1]
    return values


def _tunnel_device_codes(configured: int, reported: int) -> tuple[int, ...]:
    """Return bounded SMG tunnel candidates without treating cloud code as wire code."""
    values: list[int] = []
    if configured:
        values.append(
            SMG_TUNNEL_DEVICE_CODE
            if configured == SMG_CLOUD_DEVICE_CODE
            else configured
        )
    if reported in SMG_REPORTED_COLLECTOR_CODES:
        values.append(SMG_TUNNEL_DEVICE_CODE)
    if reported:
        values.append(reported)
    values.append(SMG_TUNNEL_DEVICE_CODE)
    return tuple(dict.fromkeys(value for value in values if 0 < value <= 0xFFFF))


async def _read_serial(send: SendCommand, route: SmgRoute) -> str:
    """Read a printable inverter serial number without making it identity-critical."""
    try:
        words = await read_holding_registers(send, route, _SERIAL_START, _SERIAL_COUNT)
    except (TimeoutError, ProtocolError):
        return ""
    chars: list[str] = []
    for word in words:
        for byte in (word >> 8, word & 0xFF):
            if byte in (0, 0xFF):
                continue
            char = chr(byte)
            if char.isalnum() or char in " -_/.":
                chars.append(char)
    serial = "".join(chars).strip()
    return serial if any(char.isalnum() and char != "0" for char in serial) else ""


async def _read_identity_metadata(send: SendCommand, route: SmgRoute) -> dict[str, Any]:
    """Collect optional, read-only model anchors; failures never block telemetry."""
    result: dict[str, Any] = {"protocol": SMG_PROTOCOL}
    for register, key in (
        (171, "model_code"),
        (184, "layout_code"),
        (643, "rated_power"),
    ):
        try:
            words = await read_holding_registers(send, route, register, 1)
        except (TimeoutError, ProtocolError):
            continue
        result[key] = words[0]
    return result
