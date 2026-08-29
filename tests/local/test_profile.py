"""Tests for the verified P17 field profile."""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.local.profile import (
    CommandNotSupported,
    parse_command_response,
)
from custom_components.dessmonitor.local.protocol import (
    ProtocolError,
    build_p17_response,
)


def test_parse_verified_general_status_fields() -> None:
    """Known P17 indices and scales become canonical integration titles."""
    raw = "2300,500,2295,499,1200,987,42,544,0,12,3,0,88,31,0,0,650,0,3210,0"
    values = parse_command_response("GS", build_p17_response("D", raw))

    assert values["Grid Voltage"] == 230.0
    assert values["Output Active Power"] == 987
    assert values["Battery Voltage"] == 54.4
    assert values["State of Charge"] == 88
    assert values["PV1 Charger Power"] == 650
    assert values["PV1 Voltage"] == 321.0


def test_parse_status_requires_verified_shape() -> None:
    """Short variants are rejected instead of assigning misleading labels."""
    with pytest.raises(ProtocolError, match="expected at least"):
        parse_command_response("GS", build_p17_response("D", "1,2,3"))


def test_parse_mode_normalizes_known_values() -> None:
    """Profile mode values align with existing DessMonitor enum names."""
    assert parse_command_response("MOD", build_p17_response("D", "03")) == {
        "Operating mode": "Battery"
    }


def test_parse_length_prefixed_serial() -> None:
    """Collector padding is removed without trimming valid identifier digits."""
    assert parse_command_response("ID", build_p17_response("D", "08ABCD12340000")) == {
        "ID": "ABCD1234"
    }


def test_nak_is_reported_as_unsupported() -> None:
    """Explicit NAKs are distinct from corruption and transient timeouts."""
    with pytest.raises(CommandNotSupported):
        parse_command_response("GS2", build_p17_response("N"))
