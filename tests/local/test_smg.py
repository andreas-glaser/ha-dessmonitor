"""Tests for read-only SMG discovery, decoding, and polling."""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.local.modbus import (
    ModbusError,
    build_read_holding_response,
    crc16_modbus,
)
from custom_components.dessmonitor.local.smg import (
    SMG_TUNNEL_COLLECTOR_ADDRESS,
    SMG_TUNNEL_DEVICE_CODE,
    decode_live_registers,
    discover_smg,
    poll_smg,
)


def _live_registers() -> list[int]:
    """Return a plausible complete 201..234 SMG block."""
    values = [0] * 34

    def set_register(register: int, value: int) -> None:
        values[register - 201] = value & 0xFFFF

    set_register(201, 3)
    set_register(202, 2301)
    set_register(203, 5000)
    set_register(204, -120)
    set_register(210, 2298)
    set_register(211, 52)
    set_register(212, 5001)
    set_register(213, 1180)
    set_register(214, 1230)
    set_register(215, 523)
    set_register(217, -400)
    set_register(219, 3205)
    set_register(220, 43)
    set_register(223, 1380)
    set_register(225, 19)
    set_register(226, 36)
    set_register(227, 41)
    set_register(229, 82)
    set_register(232, -76)
    return values


def _request_fields(payload: bytes) -> tuple[int, int, int, int]:
    """Validate and decode a Modbus read request from the driver."""
    assert len(payload) == 8
    assert int.from_bytes(payload[-2:], "little") == crc16_modbus(payload[:-2])
    return (
        payload[0],
        payload[1],
        int.from_bytes(payload[2:4], "big"),
        int.from_bytes(payload[4:6], "big"),
    )


def _ascii_registers(value: str, count: int) -> list[int]:
    """Encode two ASCII characters per register."""
    raw = value.encode("ascii").ljust(count * 2, b"\x00")[: count * 2]
    return [int.from_bytes(raw[index : index + 2], "big") for index in range(0, len(raw), 2)]


def test_live_decoder_uses_canonical_titles_and_scaling() -> None:
    """The SMG profile maps onto existing recorder-stable entity keys."""
    values = decode_live_registers(tuple(_live_registers()))
    assert values["Operating mode"] == "Off-Grid Mode"
    assert values["Grid Voltage"] == 230.1
    assert values["Output Active Power"] == 1180
    assert values["Battery Voltage"] == 52.3
    assert values["Battery Power"] == -400
    assert values["State of Charge"] == 82
    assert values["Battery Current"] == -7.6


def test_live_decoder_rejects_empty_and_implausible_blocks() -> None:
    """Zero-filled and shape-invalid replies cannot create phantom devices."""
    with pytest.raises(ModbusError, match="no usable data"):
        decode_live_registers(tuple([0] * 34))
    invalid = _live_registers()
    invalid[0] = 99
    with pytest.raises(ModbusError, match="operating mode"):
        decode_live_registers(tuple(invalid))


async def test_discovery_and_poll_send_only_function_three_reads() -> None:
    """Discovery identifies the SMG tunnel and every command remains read-only."""
    calls: list[tuple[int, int, int, int, int, int]] = []

    async def send(payload: bytes, device_code: int, collector_address: int) -> bytes:
        slave, function, register, count = _request_fields(payload)
        calls.append(
            (device_code, collector_address, slave, function, register, count)
        )
        if device_code != 1 or collector_address != 0xFF or slave != 1:
            return b""
        if register == 201:
            values = _live_registers()
        elif register == 186:
            values = _ascii_registers("SMG123456789", count)
        elif register == 171:
            values = [0x1E00]
        elif register == 184:
            values = [1]
        elif register == 643:
            values = [6200]
        elif register == 100:
            values = [0, 2]
        elif register == 108:
            values = [0, 4]
        else:
            return b""
        return build_read_holding_response(slave, values)

    devices = await discover_smg(
        send,
        collector_product_number="PN123456789012",
        configured_device_code=2376,
        max_address=2,
    )
    assert len(devices) == 1
    device = devices[0]
    assert device.route.device_code == SMG_TUNNEL_DEVICE_CODE
    assert device.route.collector_address == SMG_TUNNEL_COLLECTOR_ADDRESS
    assert device.serial == "SMG123456789"
    assert "6200W" in device.model

    values = await poll_smg(send, device.route, include_status=True)
    assert values["Fault Code"] == 2
    assert values["Warning Code"] == 4
    assert calls
    assert {call[3] for call in calls} == {3}


async def test_reported_collector_code_258_prefers_standard_smg_tunnel() -> None:
    """Known EyeBond SMG heartbeats avoid slow unrelated P17/tunnel probes."""
    routes: list[tuple[int, int]] = []

    async def send(payload: bytes, device_code: int, collector_address: int) -> bytes:
        slave, function, register, count = _request_fields(payload)
        routes.append((device_code, collector_address))
        if device_code != 1 or collector_address != 0xFF or slave != 1:
            return b""
        if register == 201:
            values = _live_registers()
        elif register == 186:
            values = _ascii_registers("SMG123456789", count)
        elif register in (171, 184, 643):
            values = [0]
        else:
            return b""
        return build_read_holding_response(slave, values)

    devices = await discover_smg(
        send,
        collector_product_number="PN123456789012",
        reported_device_code=258,
        max_address=1,
    )

    assert devices
    assert routes[0] == (1, 0xFF)
