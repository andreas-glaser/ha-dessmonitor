"""PI18 regressions using synthetic specification data and independent CRCs."""

from __future__ import annotations

from binascii import crc_hqx

import pytest

from custom_components.dessmonitor.local.discovery import DiscoveryError, discover_p17
from custom_components.dessmonitor.local.drivers import P17Driver
from custom_components.dessmonitor.local.profile import (
    CommandNotSupported,
    parse_command_response,
)
from custom_components.dessmonitor.local.protocol import (
    ProtocolError,
    build_p17_response,
)

# PI18_InfiniSolar-V-protocol-20170926, GS: 28 fields in protocol order.
PI18_STATUS = (
    "2300,500,2295,499,1200,0987,042,544,543,542,003,012,088,031,"
    "032,033,0650,0450,3210,3100,0,2,2,1,1,2,1,0"
)


def pi18_response(data: str) -> bytes:
    """Encode a synthetic device response without production framing helpers."""
    content = f"^D{len(data) + 3:03d}{data}".encode("ascii")
    return content + crc_hqx(content, 0).to_bytes(2, "big") + b"\r"


@pytest.mark.parametrize("device_code", [2452, 258])
async def test_pi18_discovery_and_polling_use_identified_profile(device_code) -> None:
    """PI18 uses its own fields and commands regardless of the tunnel code."""
    commands = []
    responses = {
        "PI": "18",
        "ID": "080123450000000000000000",
        "VFW": "12345,67890,00000",
        "PIRI": "2300,100,2300,500,100,5000,4500,480,440,420,460,560,540,2,10,060,0,1,2,1,0,0,0,1,2",
        "GS": PI18_STATUS,
        "MOD": "03",
        "ET": "00000083",
    }

    async def send(payload, code, address):
        assert code == device_code
        assert address == 1
        assert payload.startswith(b"^P"), "a telemetry driver must only send polls"
        assert payload[-3:-1] == crc_hqx(payload[:-3], 0).to_bytes(2, "big")
        command = payload[5:-3].decode("ascii")
        commands.append(command)
        if command not in responses:
            return b"^0\x8b\xa6\r"
        return pi18_response(responses[command])

    driver = P17Driver()
    (device,) = await driver.discover(
        send,
        collector_product_number="TEST-COLLECTOR",
        configured_device_code=device_code,
        reported_device_code=0,
        max_address=1,
    )
    assert device.serial == "01234500"
    assert device.entity_device_code == device_code
    assert device.driver_key == "p17"
    assert device.values["Battery Charging Current"] == 12
    assert device.values["Battery Discharge Current"] == 3
    assert device.values["PV2 Charger Power"] == 450
    assert device.values["PV2 Voltage"] == 310.0
    assert device.values["Inverter Heat Sink Temperature"] == 31
    assert device.values["Operating mode"] == "Battery"
    assert device.firmware == "12345,67890,00000"
    assert device.metadata["rated_output_power"] == 4500
    assert device.metadata["rated_battery_voltage"] == 48.0
    assert (await driver.poll(send, device, cycle=12))["Energy Total"] == 83
    assert set(commands) == set(responses)


@pytest.mark.parametrize("protocol_id", ["30", "PRIVATE-UNKNOWN"])
async def test_discovery_rejects_unimplemented_protocol(protocol_id) -> None:
    """A valid CRC does not justify interpreting another protocol as P17."""
    commands = []

    async def send(payload, _code, _address):
        commands.append(payload[5:-3])
        return pi18_response(protocol_id)

    with pytest.raises(DiscoveryError, match="no P17-compatible"):
        await discover_p17(
            send,
            collector_product_number="TEST",
            configured_device_code=2452,
            max_address=1,
        )
    assert commands == [b"PI"]


@pytest.mark.parametrize("count", [0, 19, 20, 27])
def test_pi18_rejects_incomplete_status(count) -> None:
    """A short frame must not quietly use the older P17 field layout."""
    raw = ",".join(PI18_STATUS.split(",")[:count])
    with pytest.raises(ProtocolError, match="expected at least 28"):
        parse_command_response("GS", pi18_response(raw), protocol_id="18")


@pytest.mark.parametrize("firmware", ["12345,67890,00000", "00001,00002,00030"])
def test_pi18_preserves_all_firmware_digits(firmware) -> None:
    """CPU versions have no string-length prefix or removable zero padding."""
    assert parse_command_response("VFW", pi18_response(firmware), protocol_id="18") == {
        "VFW": firmware
    }


@pytest.mark.parametrize("command", ["GS2", "GMN"])
def test_pi18_does_not_decode_p17_only_commands(command) -> None:
    """Even an unsolicited response cannot overlay PI18 values with P17 fields."""
    with pytest.raises(CommandNotSupported):
        parse_command_response(command, pi18_response("0,3100,9999"), protocol_id="18")


async def test_each_inverter_address_selects_its_own_profile() -> None:
    """One collector's first inverter must not dictate another address's layout."""

    async def send(payload, _code, address):
        command = payload[5:-3].decode("ascii")
        if address == 1:
            responses = {"PI": "17", "ID": "08ABCD12340000", "VFW": "031.0000"}
            return (
                build_p17_response("D", responses[command])
                if command in responses
                else build_p17_response("N")
            )
        responses = {
            "PI": "18",
            "ID": "080123450000000000000000",
            "VFW": "12345,67890,00000",
        }
        assert command != "GMN"
        return (
            pi18_response(responses[command])
            if command in responses
            else b"^0\x8b\xa6\r"
        )

    result = await discover_p17(
        send,
        collector_product_number="TEST",
        configured_device_code=2452,
        max_address=2,
    )
    assert [device.serial for device in result.inverters] == ["ABCD1234", "01234500"]
    assert [device.metadata["PI"] for device in result.inverters] == ["17", "18"]
    assert [device.metadata["VFW"] for device in result.inverters] == [
        "1.0",
        "12345,67890,00000",
    ]
