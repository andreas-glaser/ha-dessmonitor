"""Tests for strict local collector and inverter framing."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.dessmonitor.local.protocol import (
    FC_FORWARD_TO_DEVICE,
    HEADER_SIZE,
    MAX_FRAME_SIZE,
    ProtocolError,
    build_forward_request,
    build_heartbeat_request,
    build_p17_poll,
    build_p17_response,
    crc16_xmodem,
    decode_header,
    encode_header,
    parse_p17_response,
    parse_transport_frame,
)


def test_crc16_xmodem_standard_vector() -> None:
    """Use the standard independent CRC-16/XMODEM check value."""
    assert crc16_xmodem(b"123456789") == 0x31C3


def test_transport_frame_round_trip() -> None:
    """Transport headers preserve all request metadata and payload bytes."""
    payload = build_p17_poll("PI")
    frame = build_forward_request(0x1234, payload, 0x0994, 7)

    header, parsed_payload = parse_transport_frame(frame)

    assert header.transaction_id == 0x1234
    assert header.device_code == 0x0994
    assert header.device_address == 7
    assert header.function_code == FC_FORWARD_TO_DEVICE
    assert parsed_payload == payload


@pytest.mark.parametrize("total_length", [HEADER_SIZE - 1, MAX_FRAME_SIZE + 1])
def test_transport_rejects_out_of_bounds_length(total_length: int) -> None:
    """Builders cannot create underflowing or resource-exhausting frames."""
    with pytest.raises(ProtocolError):
        encode_header(1, 1, total_length, 1, 1)


def test_transport_rejects_declared_length_mismatch() -> None:
    """Complete-frame parsing requires the exact declared byte count."""
    frame = encode_header(1, 1, HEADER_SIZE + 2, 1, 1) + b"x"
    with pytest.raises(ProtocolError, match="declares"):
        parse_transport_frame(frame)


def test_decode_header_requires_exact_header() -> None:
    """Trailing or missing bytes cannot be mistaken for header data."""
    with pytest.raises(ProtocolError, match="exactly"):
        decode_header(b"\x00" * (HEADER_SIZE + 1))


def test_heartbeat_uses_utc_fields_and_interval() -> None:
    """Heartbeat payload uses calendar fields rather than a Unix timestamp."""
    now = datetime(2026, 8, 29, 3, 4, 5, tzinfo=timezone.utc)
    header, payload = parse_transport_frame(build_heartbeat_request(9, 30, now))

    assert header.transaction_id == 9
    assert payload == bytes((26, 8, 29, 3, 4, 5, 0, 30))


def test_p17_poll_known_shape() -> None:
    """Read-only commands contain a declared length, CRC, and CR terminator."""
    frame = build_p17_poll("PI")

    assert frame.startswith(b"^P005PI")
    assert frame.endswith(b"\r")
    assert len(frame) == 10


def test_p17_response_round_trip() -> None:
    """A valid response is decoded only after its CRC is checked."""
    parsed = parse_p17_response(build_p17_response("D", "17"))
    assert parsed.response_type == "D"
    assert parsed.data == "17"


@pytest.mark.parametrize("index", [-2, 2, 5])
def test_p17_response_rejects_tampering(index: int) -> None:
    """Changes to CRC, declared length, or payload are rejected."""
    frame = bytearray(build_p17_response("D", "17"))
    frame[index] ^= 1
    with pytest.raises(ProtocolError):
        parse_p17_response(bytes(frame))


def test_p17_response_rejects_trailing_data() -> None:
    """A valid prefix cannot hide unvalidated trailing bytes."""
    frame = build_p17_response("D", "17")
    with pytest.raises(ProtocolError):
        parse_p17_response(frame[:-1] + b"x\r")
