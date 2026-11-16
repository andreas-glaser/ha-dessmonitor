"""Setter framing, checked against independently encoded wire bytes.

The CRCs here are computed with ``binascii.crc_hqx`` rather than with the
production helper, so a change to either side of the encoding has to be made
twice to go unnoticed.
"""

from __future__ import annotations

from binascii import crc_hqx

import pytest

from custom_components.dessmonitor.local.protocol import (
    ProtocolError,
    build_p17_setter,
    build_pi30_setter,
    parse_p17_response,
)

_STUFFED = (0x28, 0x0A, 0x0D)


def _crc(content: bytes, *, escape: bool = True) -> bytes:
    """Encode a CRC the way each protocol carries it."""
    raw = crc_hqx(content, 0).to_bytes(2, "big")
    if not escape:
        return raw
    return bytes(byte + 1 if byte in _STUFFED else byte for byte in raw)


@pytest.mark.parametrize(
    "command",
    ["POP02", "PCP01", "PBT02", "PCVV58.0", "PBFT54.0", "PSDV42.0", "PGR01", "F50", "MUCHGC030"],
)
def test_a_pi30_setter_is_the_command_its_crc_and_a_terminator(command) -> None:
    """PI30 sends the command text exactly as the vendor documents it."""
    expected = command.encode("ascii")
    assert build_pi30_setter(command) == expected + _crc(expected) + b"\r"


@pytest.mark.parametrize(
    ("command", "length"),
    [("POP0", 7), ("PCP0,1", 9), ("PSDV450", 10), ("MCHGV552,540", 15), ("BUCD440,480", 14), ("MCHGC0,030", 13)],
)
def test_a_pi18_setter_declares_its_own_length(command, length) -> None:
    """The caret form counts its length field the way the read form does.

    ``POP0`` is four characters and is sent as ``^S007POP0``: three for the
    length field itself plus the command text.
    """
    content = f"^S{length:03d}{command}".encode("ascii")
    assert build_p17_setter(command, escape_crc=False) == content + _crc(
        content, escape=False
    ) + b"\r"
    assert build_p17_setter(command) == content + _crc(content) + b"\r"


def test_a_p17_setter_stuffs_the_reserved_crc_bytes() -> None:
    """P17 escapes the three bytes the transport reserves; PI18 does not."""
    escaped = build_p17_setter("PCP0,2")
    raw = build_p17_setter("PCP0,2", escape_crc=False)
    assert escaped[:-3] == raw[:-3]
    assert all(byte not in _STUFFED for byte in escaped[-3:-1])


@pytest.mark.parametrize(
    ("builder", "command"),
    [
        (build_pi30_setter, "QPIGS"),
        (build_pi30_setter, "QPIRI"),
        (build_pi30_setter, "RTEY"),
        (build_pi30_setter, "PF"),
        (build_p17_setter, "DAT190518224530"),
        (build_p17_setter, "PF"),
        (build_p17_setter, "LON1"),
    ],
)
def test_an_undeclared_command_cannot_be_framed(builder, command) -> None:
    """Only the commands a setting declares may reach an inverter.

    The builders hold the list, so a command this integration has no setting
    for - an inquiry, a factory reset, a data-log erase, a clock write whose
    digit count two sources disagree on - cannot be sent even by mistake.
    """
    with pytest.raises(ProtocolError):
        builder(command)


@pytest.mark.parametrize("builder", [build_pi30_setter, build_p17_setter])
@pytest.mark.parametrize("argument", ["X", "0;QPIGS", " 0", "0 0", "0\r"])
def test_a_non_numeric_argument_cannot_be_framed(builder, argument) -> None:
    """Every documented setter takes digits, a dot, a comma or a sign."""
    with pytest.raises(ProtocolError):
        builder(f"POP{argument}")


@pytest.mark.parametrize("builder", [build_pi30_setter, build_p17_setter])
def test_a_setter_without_a_value_is_refused(builder) -> None:
    """A bare command name is a different command on both protocols."""
    with pytest.raises(ProtocolError):
        builder("POP")


def test_a_pi30_acknowledgement_is_recognised() -> None:
    """``(ACK`` is success and ``(NAK`` is a refusal, both CRC-checked."""
    for data, response_type in (("ACK", "A"), ("NAK", "N")):
        content = f"({data}".encode("ascii")
        assert parse_p17_response(content + _crc(content) + b"\r").response_type == (
            response_type
        )


def test_a_pi18_acknowledgement_is_recognised() -> None:
    """PI18 answers a setter with ``^1`` or ``^0`` and no payload."""
    for marker, response_type in ((b"^1", "A"), (b"^0", "N")):
        assert parse_p17_response(
            marker + _crc(marker, escape=False) + b"\r", escape_crc=False
        ).response_type == response_type


def test_an_acknowledgement_with_a_wrong_crc_is_rejected() -> None:
    """A corrupted reply is never read as a successful write."""
    with pytest.raises(ProtocolError, match="CRC"):
        parse_p17_response(b"(ACK\x00\x00\r")
