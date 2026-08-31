"""Tests for the strict read-only Modbus RTU boundary."""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.local.modbus import (
    ModbusError,
    build_read_holding_request,
    build_read_holding_response,
    crc16_modbus,
    parse_read_holding_response,
    to_signed_16,
)


def test_published_smg_read_vectors() -> None:
    """Build and parse the example frames in the SMG protocol document."""
    request = build_read_holding_request(1, 202, 3)
    assert request.hex(" ") == "01 03 00 ca 00 03 25 f5"

    registers = parse_read_holding_response(
        bytes.fromhex("01 03 06 08 fc 13 88 04 b0 f7 f3"),
        slave_address=1,
        register_count=3,
    )
    # The prose says 220.0 V, but the document's actual 0x08FC wire value is
    # 2300. The parser must follow the frame bytes, not silently "fix" them.
    assert registers == (2300, 5000, 1200)


def test_response_builder_round_trip_and_signed_conversion() -> None:
    """Simulator frames use the same validator as physical responses."""
    frame = build_read_holding_response(7, [0, 0x7FFF, 0xFFFF, 0x8000])
    assert parse_read_holding_response(
        frame, slave_address=7, register_count=4
    ) == (0, 0x7FFF, 0xFFFF, 0x8000)
    assert to_signed_16(0xFFFF) == -1
    assert to_signed_16(0x8000) == -32768


@pytest.mark.parametrize(
    "mutation, message",
    (
        (lambda frame: frame[:-1] + bytes((frame[-1] ^ 1,)), "CRC"),
        (lambda frame: bytes((2,)) + frame[1:], "slave address"),
        (lambda frame: frame[:2] + bytes((frame[2] - 2,)) + frame[3:], "byte count"),
    ),
)
def test_malformed_responses_fail_closed(mutation, message: str) -> None:
    """CRC, identity, and exact length metadata are all authoritative."""
    valid = build_read_holding_response(1, [10, 20])
    invalid = mutation(valid)
    # Recompute CRC when testing metadata rather than CRC itself.
    if message != "CRC":
        invalid = invalid[:-2] + crc16_modbus(invalid[:-2]).to_bytes(2, "little")
    with pytest.raises(ModbusError, match=message):
        parse_read_holding_response(invalid, slave_address=1, register_count=2)


def test_read_request_bounds_are_enforced() -> None:
    """The local API cannot construct oversized or wrapping requests."""
    with pytest.raises(ModbusError):
        build_read_holding_request(1, 0, 0)
    with pytest.raises(ModbusError):
        build_read_holding_request(1, 0, 126)
    with pytest.raises(ModbusError):
        build_read_holding_request(1, 0xFFFF, 2)
