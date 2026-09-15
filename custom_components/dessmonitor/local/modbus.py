"""Strict, read-only Modbus RTU helpers for local inverter drivers.

Only function code 0x03 (read holding registers) is intentionally implemented.
Keeping write frame builders out of this module makes the local-mode safety
boundary easy to audit.
"""

from __future__ import annotations

from .protocol import ProtocolError

MAX_READ_REGISTERS = 125


class ModbusError(ProtocolError):
    """Raised when a Modbus response is malformed or reports an exception."""


def crc16_modbus(data: bytes | bytearray) -> int:
    """Return the standard Modbus CRC-16 value."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def build_read_holding_request(
    slave_address: int, start_register: int, register_count: int
) -> bytes:
    """Build a bounded Modbus RTU function-03 request."""
    _validate_uint(slave_address, 8, "slave_address")
    _validate_uint(start_register, 16, "start_register")
    if not 1 <= register_count <= MAX_READ_REGISTERS:
        raise ModbusError(f"register_count must be between 1 and {MAX_READ_REGISTERS}")
    if start_register + register_count > 0x10000:
        raise ModbusError("requested register range exceeds the address space")

    frame = bytes(
        (
            slave_address,
            0x03,
            start_register >> 8,
            start_register & 0xFF,
            register_count >> 8,
            register_count & 0xFF,
        )
    )
    return frame + crc16_modbus(frame).to_bytes(2, "little")


def parse_read_holding_response(
    frame: bytes, *, slave_address: int, register_count: int
) -> tuple[int, ...]:
    """Validate and decode one exact Modbus RTU function-03 response."""
    _validate_uint(slave_address, 8, "slave_address")
    if not 1 <= register_count <= MAX_READ_REGISTERS:
        raise ModbusError("invalid expected register count")
    if len(frame) < 5:
        raise ModbusError("Modbus response is too short")

    received_crc = int.from_bytes(frame[-2:], "little")
    expected_crc = crc16_modbus(frame[:-2])
    if received_crc != expected_crc:
        raise ModbusError("Modbus response CRC does not match", reason="crc_mismatch")
    if frame[0] != slave_address:
        raise ModbusError(
            f"unexpected Modbus slave address {frame[0]} (expected {slave_address})"
        )

    function_code = frame[1]
    if function_code == 0x83:
        if len(frame) != 5:
            raise ModbusError("malformed Modbus exception response")
        raise ModbusError(
            f"Modbus exception code {frame[2]}",
            reason="modbus_exception",
            details={"exception_code": frame[2]},
        )
    if function_code != 0x03:
        raise ModbusError(f"unexpected Modbus function code {function_code}")

    expected_byte_count = register_count * 2
    if frame[2] != expected_byte_count:
        raise ModbusError(
            f"unexpected Modbus byte count {frame[2]} (expected {expected_byte_count})"
        )
    expected_length = 3 + expected_byte_count + 2
    if len(frame) != expected_length:
        raise ModbusError(
            f"Modbus response has {len(frame)} bytes (expected {expected_length})"
        )

    payload = frame[3:-2]
    return tuple(
        int.from_bytes(payload[offset : offset + 2], "big")
        for offset in range(0, len(payload), 2)
    )


def build_read_holding_response(slave_address: int, registers: list[int]) -> bytes:
    """Build a response for protocol simulators and tests."""
    _validate_uint(slave_address, 8, "slave_address")
    if not registers or len(registers) > MAX_READ_REGISTERS:
        raise ModbusError("invalid response register count")
    payload = bytearray((slave_address, 0x03, len(registers) * 2))
    for register in registers:
        _validate_uint(register, 16, "register")
        payload.extend(register.to_bytes(2, "big"))
    payload.extend(crc16_modbus(payload).to_bytes(2, "little"))
    return bytes(payload)


def to_signed_16(value: int) -> int:
    """Interpret one unsigned register as a signed 16-bit integer."""
    _validate_uint(value, 16, "register")
    return value - 0x10000 if value >= 0x8000 else value


def _validate_uint(value: int, bits: int, name: str) -> None:
    """Validate an unsigned integer without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModbusError(f"{name} must be an integer")
    if not 0 <= value < 1 << bits:
        raise ModbusError(f"{name} is outside the {bits}-bit range")
