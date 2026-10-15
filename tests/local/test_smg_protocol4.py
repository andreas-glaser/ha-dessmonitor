"""Hardware-evidence regression tests for protocol-number 4."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.dessmonitor.local.coordinator import DessMonitorLocalCoordinator
from custom_components.dessmonitor.local.drivers import (
    SmgModbusDriver,
    discover_supported_devices,
)
from custom_components.dessmonitor.local.hybrid import merge_cloud_and_local
from custom_components.dessmonitor.local.modbus import (
    ModbusError,
    build_read_holding_response,
    crc16_modbus,
)
from custom_components.dessmonitor.local.server import CollectorIdentity
from custom_components.dessmonitor.local.smg import (
    SmgRoute,
    decode_live_registers,
    discover_smg,
    poll_smg,
)
from custom_components.dessmonitor.local.smg_protocol4 import (
    PROTOCOL4_BLOCKS,
    decode_protocol4,
)
from custom_components.dessmonitor.sensor import _build_sensor_entities

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "protocol4_hardware.json"


def _sample(index=0):
    blocks = json.loads(_FIXTURE.read_text())["samples"][index]
    return {
        int(start) + i: word
        for start, words in blocks.items()
        for i, word in enumerate(words)
    }


class HardwareReplay:
    """Transport replies use recorded hardware words, never live networking."""

    def __init__(self, index=0, protocol=4):
        self.words = _sample(index)
        self.protocol = protocol
        self.calls = []
        self.corrupt_register = None

    async def send(self, payload, code, collector_address):
        assert len(payload) == 8 and crc16_modbus(payload) == 0
        assert payload[1] == 3  # All requests must be read-only.
        slave = payload[0]
        start = int.from_bytes(payload[2:4], "big")
        count = int.from_bytes(payload[4:6], "big")
        self.calls.append((slave, start, count))
        if (code, collector_address, slave) != (1, 255, 1):
            return b""
        if start == 184:
            words = [self.protocol]
        elif start == 186:
            words = [0] * count  # Exercise PN + verified address identity fallback.
        elif start == 171:
            words = [32771]
        else:
            words = [self.words.get(start + offset, 0) for offset in range(count)]
        response = build_read_holding_response(slave, words)
        if start == self.corrupt_register:
            response = response[:-1] + bytes((response[-1] ^ 1,))
        return response


@pytest.mark.parametrize(
    "index,power,voltage,current", [(0, 807, 245.0, 0.5), (1, 787, 244.2, 0.6)]
)
def test_recorded_snapshots_decode(index, power, voltage, current):
    values = decode_protocol4(_sample(index))
    assert values["Battery Voltage"] == 53.3
    assert values["SOC"] == 75
    assert "State of Charge" not in values  # Preserve the existing SOC sensor.
    assert values["Output Active Power"] == power
    assert values["Grid Voltage"] == voltage
    assert values["Inverter Current"] == current
    assert values["Inverter frequency"] == 50.0
    assert values["INV Module Termperature"] == 47
    assert values["Energy Today"] == 12.33
    assert values["Energy Total"] == 314.83
    assert values["Battery Current"] == 0


def test_power_and_flags_are_not_current_and_frequency():
    words = _sample()
    words[206] = 3425
    words[207] = 772
    words[278] = 65536 - 125
    values = decode_protocol4(words)
    assert values["AC charging power"] == 3425
    assert values["Inverter Current"] == 0.5
    assert values["Inverter frequency"] == 50
    assert values["Battery Current"] == -12.5
    assert values["Battery Charging Current"] == 0
    assert values["Battery Discharge Current"] == 12.5


def test_daytime_capture_has_solar_production_and_battery_charging():
    """Third hardware sample exercises nonzero PV and an unsigned energy word."""
    values = decode_protocol4(_sample(2))
    assert values["Operating mode"] == "Off-grid Mode"
    assert values["Battery Voltage"] == 53.1
    assert values["SOC"] == 32
    assert values["Battery Current"] == 21.7
    assert values["Battery Charging Current"] == 21.7
    assert values["Battery Discharge Current"] == 0
    assert values["Output Active Power"] == 1009
    assert values["PV Power"] == 2303
    assert values["PV1 Voltage"] == 258.4
    assert values["PV1 Charger Current"] == 4.3
    assert values["PV1 Charger Power"] == 1127
    assert values["PV2 Voltage"] == 259.1
    assert values["PV2 Charger Current"] == 4.5
    assert values["PV2 Charger Power"] == 1177
    assert values["Energy Today"] == 7.04
    assert values["Energy Total"] == 337.23


def test_incomplete_and_invalid_snapshot_rejected():
    words = _sample()
    del words[277]
    with pytest.raises(ModbusError, match="incomplete"):
        decode_protocol4(words)
    words = _sample()
    words[280] = 65535
    with pytest.raises(ModbusError, match="SOC"):
        decode_protocol4(words)
    words = {address: 0 for address in _sample()}
    with pytest.raises(ModbusError, match="voltage"):
        decode_protocol4(words)


async def test_discovery_retains_layout_for_every_poll():
    replay = HardwareReplay()
    driver, (device,) = await discover_supported_devices(
        replay.send,
        collector_product_number="TEST",
        reported_device_code=258,
        device_address=1,
    )
    assert isinstance(driver, SmgModbusDriver)
    assert device.metadata["layout_code"] == 4
    assert "rated_power" not in device.metadata
    assert "protocol 4" in device.model
    assert device.entity_device_code == 6544
    assert replay.calls[0] == (1, 184, 1)
    assert (1, 201, 34) not in replay.calls
    assert (1, 643, 1) not in replay.calls
    replay.calls.clear()
    values = await driver.poll(replay.send, device, cycle=6)
    assert values["SOC"] == 75
    assert replay.calls == [(1, start, count) for start, count in PROTOCOL4_BLOCKS]


async def test_corrupt_block_fails_cycle_instead_of_publishing_partial_values():
    replay = HardwareReplay()
    replay.corrupt_register = 277
    with pytest.raises(ModbusError):
        await poll_smg(replay.send, SmgRoute(1, 255, 1, 4))
    assert replay.calls.count((1, 277, 5)) == 2
    assert (1, 302, 4) not in replay.calls


async def test_mixed_collector_retains_each_inverters_register_layout():
    """One protocol-4 slave must not switch a neighbour's legacy SMG map."""
    replay = HardwareReplay()
    calls = []

    async def send(payload, code, address):
        slave = payload[0]
        start = int.from_bytes(payload[2:4], "big")
        count = int.from_bytes(payload[4:6], "big")
        assert payload[1] == 3 and crc16_modbus(payload) == 0
        calls.append((slave, start, count))
        if start == 186:
            # Distinct serials permit discovery to continue past the first slave.
            return build_read_holding_response(slave, [0x4130 + slave] + [0] * 11)
        if slave == 1:
            return await replay.send(payload, code, address)
        if slave != 2:
            return b""
        if start == 184:
            words = [1]
        elif start == 201:
            assert count == 34
            words = [0] * count
            for register, value in {201: 3, 202: 2300, 215: 523, 229: 82}.items():
                words[register - 201] = value
        else:
            words = [0] * count
        return build_read_holding_response(slave, words)

    driver = SmgModbusDriver()
    devices = await driver.discover(
        send,
        collector_product_number="TEST",
        configured_device_code=0,
        reported_device_code=258,
        max_address=2,
    )
    assert [device.metadata["layout_code"] for device in devices] == [4, 1]
    assert [device.entity_device_code for device in devices] == [6544, 2376]
    calls.clear()
    modern = await driver.poll(send, devices[0], cycle=1)
    legacy = await driver.poll(send, devices[1], cycle=1)
    assert modern["Battery Voltage"] == 53.3 and modern["SOC"] == 75
    assert legacy["Battery Voltage"] == 52.3 and legacy["State of Charge"] == 82
    assert (1, 201, 34) not in calls
    assert (2, 201, 34) in calls


async def test_unsupported_layout_cannot_fall_back_to_standard_map():
    replay = HardwareReplay(protocol=5)

    async def send(payload, code, address):
        response = await replay.send(payload, code, address)
        # Both candidate collector routes identify the same unsupported layout.
        if int.from_bytes(payload[2:4], "big") == 184:
            return build_read_holding_response(payload[0], [5])
        return response

    with pytest.raises(ModbusError, match="no SMG"):
        await discover_smg(send, collector_product_number="TEST", device_address=1)
    assert all(start == 184 for _, start, _ in replay.calls)


def test_original_false_positive_with_zero_voltages_is_rejected():
    # The actual old 201..234 capture: valid CRC and mode, but wrong layout.
    words = [0] * 34
    for address, value in {
        201: 2,
        203: 5001,
        206: 3425,
        207: 772,
        227: 5001,
        230: 631,
        231: 55,
    }.items():
        words[address - 201] = value
    with pytest.raises(ModbusError, match="voltage"):
        decode_live_registers(tuple(words))


async def test_hardware_values_reach_existing_hybrid_entities(hass):
    replay = HardwareReplay()
    driver = SmgModbusDriver()
    (device,) = await driver.discover(
        replay.send,
        collector_product_number="TEST",
        configured_device_code=0,
        reported_device_code=258,
        max_address=1,
    )
    # Run the actual coordinator conversion: it filters unsupported sensor titles.
    local = object.__new__(DessMonitorLocalCoordinator)
    local._identity = CollectorIdentity("TEST", "192.168.10.58", 258)
    local._device_code = 1
    local._devices = {device.serial: device}
    local._polled_serials = {device.serial}
    local_data = local._coordinator_data()

    cloud = {
        "CLOUD": {
            "collector": {"pn": "TEST"},
            "device": {"devcode": 6544, "devaddr": 1, "alias": "Home"},
            "data": [
                {"title": "SOC", "val": "60", "unit": "%"},
                {"title": "Battery Voltage", "val": "54", "unit": "V"},
                {"title": "INV Module Termperature", "val": "55", "unit": "C"},
                {"title": "DC Module Termperature", "val": "40", "unit": "C"},
                {"title": "Total Output Active Power", "val": "999", "unit": "W"},
                {"title": "PV temperature", "val": "30", "unit": "C"},
                {"title": "Main Output Priority", "val": "SUB", "unit": ""},
                {"title": "Current output priority", "val": "SBU", "unit": ""},
                {"title": "Charger Source Priority", "val": "SOR", "unit": ""},
                {"title": "Current charging priority", "val": "SNU", "unit": ""},
                {"title": "Output Voltage Setting", "val": "230V", "unit": "V"},
            ],
        }
    }
    coordinator = MagicMock(hass=hass, data=cloud)
    known = set()
    entities = _build_sensor_entities(coordinator, known)
    previous_ids = {entity.unique_id for entity in entities}
    coordinator.data = merge_cloud_and_local(cloud, local_data, local_available=True)
    entities += _build_sensor_entities(coordinator, known)
    by_type = {entity._sensor_type: entity for entity in entities}
    assert previous_ids.issubset({entity.unique_id for entity in entities})
    assert by_type["SOC"].native_value == 75
    assert "State of Charge" not in by_type
    assert by_type["Battery Voltage"].native_value == 53.3
    assert by_type["Output Active Power"].native_value == 807
    assert by_type["INV Module Termperature"].native_value == 47
    assert by_type["DC Module Termperature"].native_value == 42
    assert by_type["PV Temperature"].native_value == 36
    assert by_type["Output priority"].native_value == "Solar → Utility → Battery"
    assert by_type["Charger Source Priority"].native_value == "Solar or Utility"
    assert by_type["Output Voltage Setting"].native_value == 230
    assert by_type["Data Source"].native_value == "Local"
    # Main/current cloud controls remain independently readable after merging.
    points = {
        point["title"]: point["val"] for point in coordinator.data["CLOUD"]["data"]
    }
    assert points["Main Output Priority"] == "SUB"
    assert points["Current output priority"] == "SBU"
