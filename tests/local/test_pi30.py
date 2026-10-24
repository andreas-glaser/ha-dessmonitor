"""Read-only PI30 interoperability with independently encoded wire frames."""

from __future__ import annotations

import asyncio
from binascii import crc_hqx

import pytest

from custom_components.dessmonitor.local.diagnostics import ProbeDiagnostics
from custom_components.dessmonitor.local.drivers import (
    LocalDevice,
    Pi30Driver,
    discover_supported_devices,
)
from custom_components.dessmonitor.local.pi30 import (
    discover_pi30,
    parse_pi30_response,
    query_pi30,
)
from custom_components.dessmonitor.local.protocol import ProtocolError, build_pi30_poll

STATUS = (
    "230.0 50.0 229.5 49.9 1200 0987 042 400 12.80 012 088 0031 "
    "0014 103.8 12.75 00003 00110110 00 00 00180 010"
)


def wire(content: bytes) -> bytes:
    crc = crc_hqx(content, 0).to_bytes(2, "big")
    return content + bytes(x + 1 if x in (0x28, 0x0A, 0x0D) else x for x in crc) + b"\r"


@pytest.mark.parametrize("route", [(2452, 1), (2452, 255), (258, 255)])
async def test_discovery_and_polling_identify_pi30_on_known_routes(route) -> None:
    commands = []

    async def send(payload, code, address):
        if not payload.startswith(b"Q") or (code, address) != route:
            return b""
        assert payload == wire(payload[:-3])
        command = payload[:-3].decode("ascii")
        commands.append(command)
        responses = {
            "QPI": "PI30",
            "QID": "12345678901234",
            "QVFW": "VERFW:00001.20",
            "QPIGS": STATUS,
            "QMOD": "B",
        }
        return wire(b"(" + responses.get(command, "NAK").encode("ascii"))

    driver, devices = await discover_supported_devices(
        send,
        collector_product_number="TEST",
        configured_device_code=2452 if route[0] == 2452 else 258,
        max_address=1,
    )
    assert driver.key == "pi30"
    assert len(devices) == 1
    device = devices[0]
    assert (device.transport_device_code, device.collector_address) == route
    assert device.device_address == 1
    assert device.serial == "12345678901234"
    values = await driver.poll(send, device, cycle=12)
    assert values["Battery Voltage"] == 12.8
    assert values["Battery Charging Current"] == 12
    assert values["Battery Discharge Current"] == 3
    assert values["PV Charging Current"] == 14
    assert values["PV Charge Power"] == 180
    assert values["Output Active Power"] == 987
    assert values["Operating mode"] == "Battery"
    assert set(commands) <= {"QPI", "QID", "QVFW", "QPIRI", "QPIGS", "QMOD"}


@pytest.mark.parametrize("command", ["POP02", "PBDV10.5", "QPI\rPOP02", "", "QUNKNOWN"])
async def test_queries_cannot_send_writes_or_unimplemented_commands(command) -> None:
    async def send(*_args):
        pytest.fail("invalid command reached the transport")

    with pytest.raises(ProtocolError, match="read-only"):
        await query_pi30(send, 2452, 1, 1, command)


def test_pi30_wire_format_and_standard_status_prefix() -> None:
    assert build_pi30_poll("QPI") == bytes.fromhex("51 50 49 be ac 0d")
    assert parse_pi30_response("QPI", bytes.fromhex("28 50 49 33 30 9a 0b 0d")) == {
        "PI": "30"
    }
    base = " ".join(STATUS.split()[:17])
    values = parse_pi30_response("QPIGS", wire(b"(" + base.encode()))
    assert values["Battery Voltage"] == 12.8
    assert "PV Charge Power" not in values


@pytest.mark.parametrize("data", ["PI18", "PI41", "PI30 ", "ACK", "NAK"])
def test_other_protocols_and_acknowledgements_cannot_identify_pi30(data) -> None:
    with pytest.raises(ProtocolError):
        parse_pi30_response("QPI", wire(b"(" + data.encode()))


@pytest.mark.parametrize(
    "index,value",
    [
        (8, "nan"),
        (8, "inf"),
        (8, "-1"),
        (8, "1e2"),
        (10, "101"),
        (16, "00000002"),
        (20, "1111"),
    ],
)
def test_invalid_status_never_becomes_telemetry(index, value) -> None:
    fields = STATUS.split()
    fields[index] = value
    with pytest.raises(ProtocolError):
        parse_pi30_response("QPIGS", wire(b"(" + " ".join(fields).encode()))


@pytest.mark.parametrize(
    "frame",
    [
        b"",
        b"(PI30\x00\x00\r",
        wire(b"(PI30")[:-1],
        wire(b"^PI30"),
        wire(b"(\xff"),
        wire(b"(" + b"0" * 4096),
    ],
)
def test_malformed_frames_are_rejected(frame) -> None:
    with pytest.raises(ProtocolError):
        parse_pi30_response("QPI", frame)


@pytest.mark.parametrize("count", [0, 16, 18, 19, 20])
def test_unknown_status_layouts_are_rejected(count) -> None:
    """A short reply, or a truncated extended block, is still not telemetry."""
    fields = (STATUS.split() + ["0"] * 7)[:count]
    with pytest.raises(
        ProtocolError, match="truncated" if count == 0 else "field count"
    ):
        parse_pi30_response("QPIGS", wire(b"(" + " ".join(fields).encode()))


async def test_identification_without_status_cannot_create_a_device() -> None:
    async def send(payload, _code, _address):
        return wire(b"(PI30") if payload == build_pi30_poll("QPI") else wire(b"(NAK")

    with pytest.raises(ProtocolError, match="valid identification and status"):
        await discover_pi30(send, collector_product_number="TEST")


@pytest.mark.parametrize("address", [5, 247])
async def test_explicit_address_and_missing_serial_discover_only_one_inverter(
    address,
) -> None:
    async def send(payload, _code, route):
        assert route == address
        data = {"QPI": "PI30", "QPIGS": STATUS}.get(payload[:-3].decode(), "NAK")
        return wire(b"(" + data.encode())

    result = await discover_pi30(
        send, collector_product_number="TEST", device_address=address
    )
    assert len(result.inverters) == 1
    assert result.inverters[0].serial == f"TEST-{address}"
    assert result.inverters[0].address == address


async def test_repeated_serial_stops_automatic_scanning() -> None:
    addresses = set()

    async def send(payload, _code, address):
        addresses.add(address)
        data = {"QPI": "PI30", "QPIGS": STATUS, "QID": "12345678901234"}.get(
            payload[:-3].decode(), "NAK"
        )
        return wire(b"(" + data.encode())

    result = await discover_pi30(send, collector_product_number="TEST")
    assert len(result.inverters) == 1
    assert addresses == {1, 2}


async def test_bad_crc_is_recorded_without_payload_disclosure() -> None:
    diagnostics = ProbeDiagnostics()

    async def send(*_args):
        return b"(PRIVATE\x00\x00\r"

    with diagnostics.capture(), pytest.raises(ProtocolError):
        await query_pi30(send, 2452, 255, 1, "QPIGS")
    attempt = diagnostics.attempts[0]
    assert attempt.outcome == "crc_mismatch"
    assert attempt.collector_address == 255
    assert attempt.device_address == 1
    assert "PRIVATE" not in str(diagnostics.as_dict())


def _device() -> LocalDevice:
    return LocalDevice(
        driver_key="pi30",
        transport_device_code=2452,
        collector_address=255,
        device_address=1,
        entity_device_code=2452,
        serial="12345678901234",
        model="PI30 inverter",
        firmware="",
        address_verified=False,
    )


async def test_unsupported_optional_mode_does_not_disable_status_polling() -> None:
    commands = []

    async def send(payload, _code, route):
        assert route == 255
        command = payload[:-3].decode()
        commands.append(command)
        return wire(b"(" + (STATUS if command == "QPIGS" else "NAK").encode())

    device = _device()
    for cycle in (1, 2):
        values = await Pi30Driver().poll(send, device, cycle=cycle)
        assert values["Battery Voltage"] == 12.8
        assert "Operating mode" not in values
    assert commands == ["QPIGS", "QMOD", "QPIGS"]


@pytest.mark.parametrize("failure", ["invalid", "timeout", "cancelled"])
async def test_primary_poll_failure_and_cancellation_are_not_hidden(failure) -> None:
    async def send(payload, _code, _route):
        assert payload == build_pi30_poll("QPIGS")
        if failure == "timeout":
            raise TimeoutError
        if failure == "cancelled":
            raise asyncio.CancelledError
        return wire(b"(NAK")

    expected = {
        "invalid": ProtocolError,
        "timeout": TimeoutError,
        "cancelled": asyncio.CancelledError,
    }[failure]
    with pytest.raises(expected):
        await Pi30Driver().poll(send, _device(), cycle=1)


@pytest.mark.parametrize("response", [b"", wire(b"(INVALID")])
async def test_optional_mode_failure_preserves_valid_status(response) -> None:
    async def send(payload, _code, _route):
        if payload == build_pi30_poll("QPIGS"):
            return wire(b"(" + STATUS.encode())
        return response

    values = await Pi30Driver().poll(send, _device(), cycle=1)
    assert values["Battery Voltage"] == 12.8
    assert "Operating mode" not in values


# Captured on a WatchPower Wi-Fi collector in issue #50: the standard 21
# fields followed by three vendor fields.
_ISSUE_50_FRAME = (
    b"(000.0 00.0 229.9 50.0 0345 0299 008 357 26.00 000 065 0031 00.1 067.9 "
    b"00.00 00017 00010000 00 00 00000 011 0 00 0000\xe9C\r"
)


def test_trailing_vendor_fields_are_ignored() -> None:
    """A 24-field QPIGS reply decodes from its standard prefix (#50)."""
    values = parse_pi30_response("QPIGS", _ISSUE_50_FRAME)
    assert values["Battery Voltage"] == 26.0
    assert values["Output Voltage"] == 229.9
    assert values["State of Charge"] == 65.0
    assert values["PV Charge Power"] == 0.0


@pytest.mark.parametrize("extra", [1, 3, 7])
def test_extra_fields_do_not_change_decoded_values(extra) -> None:
    """Whatever a firmware appends must not alter the standard readings."""
    baseline = parse_pi30_response("QPIGS", wire(b"(" + STATUS.encode()))
    padded = " ".join(STATUS.split() + ["0"] * extra)
    assert parse_pi30_response("QPIGS", wire(b"(" + padded.encode())) == baseline


def test_extended_flags_are_still_validated_in_a_longer_reply() -> None:
    """Ignoring the tail must not skip the checks on the standard fields."""
    fields = STATUS.split() + ["0", "00"]
    fields[20] = "1111"
    with pytest.raises(ProtocolError, match="extended status flags"):
        parse_pi30_response("QPIGS", wire(b"(" + " ".join(fields).encode()))
