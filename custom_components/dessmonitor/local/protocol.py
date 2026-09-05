"""Strict EyeBond transport and P17 framing helpers.

The collector transport is an eight-byte, big-endian header followed by a
bounded payload. P17 payloads carry their own length and CRC. Parsing is kept
independent of Home Assistant so malformed-device and recovery paths can be
tested without a running instance.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone

HEADER_SIZE = 8
WIRE_LENGTH_OFFSET = 6
MAX_FRAME_SIZE = 4096

FC_HEARTBEAT = 1
FC_FORWARD_TO_DEVICE = 4

P17_DEFAULT_DEVCODE = 0x0994
_CRC_STUFF_BYTES = frozenset((0x28, 0x0A, 0x0D))


class ProtocolError(ValueError):
    """Raised when a collector or inverter frame is malformed."""

    def __init__(
        self,
        message: str,
        *,
        reason: str = "invalid_response",
        details: dict[str, int] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class EyeBondHeader:
    """Decoded EyeBond transport header."""

    transaction_id: int
    device_code: int
    wire_length: int
    device_address: int
    function_code: int

    @property
    def total_length(self) -> int:
        """Return the complete transport frame length."""
        return self.wire_length + WIRE_LENGTH_OFFSET

    @property
    def payload_length(self) -> int:
        """Return the number of bytes after the transport header."""
        return self.total_length - HEADER_SIZE


@dataclass(frozen=True, slots=True)
class P17Response:
    """Validated inverter response."""

    response_type: str
    data: str


def crc16_xmodem(data: bytes, initial: int = 0) -> int:
    """Calculate CRC-16/XMODEM without a lookup table."""
    crc = initial & 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else crc << 1
    return crc & 0xFFFF


def _validate_uint(value: int, bits: int, name: str) -> None:
    """Validate an unsigned integer field."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{name} must be an integer")
    if not 0 <= value < 1 << bits:
        raise ProtocolError(f"{name} is outside the {bits}-bit range")


def encode_header(
    transaction_id: int,
    device_code: int,
    total_length: int,
    device_address: int,
    function_code: int,
) -> bytes:
    """Encode a validated EyeBond transport header."""
    _validate_uint(transaction_id, 16, "transaction_id")
    _validate_uint(device_code, 16, "device_code")
    _validate_uint(device_address, 8, "device_address")
    _validate_uint(function_code, 8, "function_code")
    if not HEADER_SIZE <= total_length <= MAX_FRAME_SIZE:
        raise ProtocolError(
            f"total_length must be between {HEADER_SIZE} and {MAX_FRAME_SIZE}"
        )
    return struct.pack(
        ">HHHBB",
        transaction_id,
        device_code,
        total_length - WIRE_LENGTH_OFFSET,
        device_address,
        function_code,
    )


def decode_header(data: bytes) -> EyeBondHeader:
    """Decode and validate one complete EyeBond header."""
    if len(data) != HEADER_SIZE:
        raise ProtocolError(f"header must be exactly {HEADER_SIZE} bytes")

    transaction_id, device_code, wire_length, device_address, function_code = (
        struct.unpack(">HHHBB", data)
    )
    header = EyeBondHeader(
        transaction_id,
        device_code,
        wire_length,
        device_address,
        function_code,
    )
    if not HEADER_SIZE <= header.total_length <= MAX_FRAME_SIZE:
        raise ProtocolError(
            f"transport frame length {header.total_length} is outside the allowed range"
        )
    return header


def parse_transport_frame(data: bytes) -> tuple[EyeBondHeader, bytes]:
    """Validate a complete transport frame and return its payload."""
    if len(data) < HEADER_SIZE:
        raise ProtocolError("transport frame is shorter than its header")
    header = decode_header(data[:HEADER_SIZE])
    if len(data) != header.total_length:
        raise ProtocolError(
            f"transport frame declares {header.total_length} bytes, received {len(data)}"
        )
    return header, data[HEADER_SIZE:]


def build_heartbeat_request(
    transaction_id: int, interval: int, now: datetime | None = None
) -> bytes:
    """Build a collector heartbeat request using UTC calendar fields."""
    if not 1 <= interval <= 0xFFFF:
        raise ProtocolError("heartbeat interval must be between 1 and 65535 seconds")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    payload = bytes(
        (
            (timestamp.year - 2000) & 0xFF,
            timestamp.month,
            timestamp.day,
            timestamp.hour,
            timestamp.minute,
            timestamp.second,
        )
    ) + struct.pack(">H", interval)
    return (
        encode_header(transaction_id, 0, HEADER_SIZE + len(payload), 1, FC_HEARTBEAT)
        + payload
    )


def parse_heartbeat_response(payload: bytes) -> str:
    """Decode and validate the collector product number."""
    if not 1 <= len(payload) <= 64:
        raise ProtocolError("collector identifier has an invalid length")
    raw = payload.rstrip(b"\x00 ")
    try:
        identifier = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise ProtocolError("collector identifier is not ASCII") from err
    if not identifier or any(
        ord(char) < 0x20 or ord(char) > 0x7E for char in identifier
    ):
        raise ProtocolError("collector identifier contains invalid characters")
    return identifier


def build_forward_request(
    transaction_id: int,
    payload: bytes,
    device_code: int,
    device_address: int,
) -> bytes:
    """Wrap an inverter command in an EyeBond forward-to-device frame."""
    total_length = HEADER_SIZE + len(payload)
    return (
        encode_header(
            transaction_id,
            device_code,
            total_length,
            device_address,
            FC_FORWARD_TO_DEVICE,
        )
        + payload
    )


def _encode_crc(content: bytes) -> bytes:
    """Return the protocol-stuffed CRC bytes for content."""
    crc = crc16_xmodem(content)
    encoded = ((crc >> 8) & 0xFF, crc & 0xFF)
    return bytes(byte + 1 if byte in _CRC_STUFF_BYTES else byte for byte in encoded)


def _ascii_command(command: str) -> bytes:
    """Validate and encode a bounded inverter command."""
    if not 1 <= len(command) <= 64:
        raise ProtocolError("P17 command must contain between 1 and 64 characters")
    try:
        encoded = command.encode("ascii")
    except UnicodeEncodeError as err:
        raise ProtocolError("P17 commands must be ASCII") from err
    if any(byte < 0x21 or byte > 0x7E for byte in encoded):
        raise ProtocolError("P17 command contains unsupported characters")
    return encoded


def build_p17_poll(command: str) -> bytes:
    """Build a P17 read-only poll command."""
    encoded = _ascii_command(command)
    content = b"^P" + f"{3 + len(encoded):03d}".encode("ascii") + encoded
    return content + _encode_crc(content) + b"\r"


def build_p17_response(response_type: str, data: str = "") -> bytes:
    """Build a P17 response, primarily for protocol simulators and tests."""
    if response_type not in {"D", "A", "N"}:
        raise ProtocolError("unsupported P17 response type")
    encoded = data.encode("ascii")
    content = (
        b"^"
        + response_type.encode("ascii")
        + f"{3 + len(encoded):03d}".encode("ascii")
        + encoded
    )
    return content + _encode_crc(content) + b"\r"


def parse_p17_response(frame: bytes) -> P17Response:
    """Parse a P17 or Q-style response with exact length and CRC validation."""
    if len(frame) < 5 or frame[-1:] != b"\r":
        raise ProtocolError("inverter response is truncated or lacks its terminator")

    if frame.startswith(b"^"):
        return _parse_caret_response(frame)
    if frame.startswith(b"("):
        return _parse_q_response(frame)
    raise ProtocolError("inverter response uses unsupported framing")


def _parse_caret_response(frame: bytes) -> P17Response:
    """Parse standard and short caret-framed responses."""
    if len(frame) == 5 and frame[1:2] in {b"0", b"1"}:
        content = frame[:2]
        if frame[2:4] != _encode_crc(content):
            raise ProtocolError(
                "inverter response CRC does not match", reason="crc_mismatch"
            )
        return P17Response("A" if frame[1:2] == b"1" else "N", "")

    if len(frame) < 8 or frame[1:2] not in {b"D", b"A", b"N"}:
        raise ProtocolError("invalid P17 response header")
    try:
        declared_length = int(frame[2:5].decode("ascii"))
    except (UnicodeDecodeError, ValueError) as err:
        raise ProtocolError("invalid P17 length field") from err
    if declared_length < 3:
        raise ProtocolError("invalid P17 declared length")

    expected_length = declared_length + 5
    if len(frame) != expected_length:
        raise ProtocolError(
            f"P17 response declares {expected_length} bytes, received {len(frame)}"
        )
    content = frame[:-3]
    if frame[-3:-1] != _encode_crc(content):
        raise ProtocolError(
            "inverter response CRC does not match", reason="crc_mismatch"
        )
    try:
        decoded = frame[5:-3].decode("ascii")
    except UnicodeDecodeError as err:
        raise ProtocolError("P17 response payload is not ASCII") from err
    return P17Response(frame[1:2].decode("ascii"), decoded)


def _parse_q_response(frame: bytes) -> P17Response:
    """Parse a Q-style response with its CRC and terminator."""
    if len(frame) < 5:
        raise ProtocolError("Q response is too short")
    content = frame[:-3]
    if frame[-3:-1] != _encode_crc(content):
        raise ProtocolError(
            "inverter response CRC does not match", reason="crc_mismatch"
        )
    try:
        decoded = frame[1:-3].decode("ascii")
    except UnicodeDecodeError as err:
        raise ProtocolError("Q response payload is not ASCII") from err
    if decoded == "ACK":
        return P17Response("A", "")
    if decoded == "NAK":
        return P17Response("N", "")
    return P17Response("D", decoded)
