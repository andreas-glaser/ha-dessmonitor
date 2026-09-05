"""End-to-end local coordinator tests with a simulated physical collector."""

from __future__ import annotations

import asyncio
import contextlib
from binascii import crc_hqx
from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dessmonitor.const import (
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_DEVICE_CODE,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
)
from custom_components.dessmonitor.local.coordinator import DessMonitorLocalCoordinator
from custom_components.dessmonitor.local.drivers import LocalDevice, P17Driver
from custom_components.dessmonitor.local.hybrid import merge_cloud_and_local
from custom_components.dessmonitor.local.modbus import (
    build_read_holding_response,
    crc16_modbus,
)
from custom_components.dessmonitor.local.protocol import (
    FC_FORWARD_TO_DEVICE,
    FC_HEARTBEAT,
    HEADER_SIZE,
    build_p17_response,
    decode_header,
    encode_header,
)
from custom_components.dessmonitor.local.server import CollectorIdentity

pytestmark = pytest.mark.usefixtures("socket_enabled")


class SimulatedCollector:
    """Minimal EyeBond collector that exposes one P17 or PI18 inverter."""

    def __init__(self, port: int, protocol_id: str = "17") -> None:
        self.port = port
        self.protocol_id = protocol_id
        self.commands: list[str] = []
        self.writer: asyncio.StreamWriter | None = None
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Connect to the integration and begin responding."""
        reader, self.writer = await asyncio.open_connection("127.0.0.1", self.port)
        self.task = asyncio.create_task(self._run(reader, self.writer))

    async def stop(self) -> None:
        """Disconnect and stop the response loop."""
        if self.writer is not None:
            self.writer.close()
            with contextlib.suppress(ConnectionError):
                await self.writer.wait_closed()
            self.writer = None
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(
                asyncio.CancelledError, asyncio.IncompleteReadError
            ):
                await self.task
            self.task = None

    async def _run(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            header = decode_header(await reader.readexactly(HEADER_SIZE))
            payload = await reader.readexactly(header.payload_length)
            if header.function_code == FC_HEARTBEAT:
                response = b"PN123456789012"
                writer.write(
                    encode_header(
                        header.transaction_id,
                        2452,
                        HEADER_SIZE + len(response),
                        1,
                        FC_HEARTBEAT,
                    )
                    + response
                )
            elif header.function_code == FC_FORWARD_TO_DEVICE:
                assert payload.startswith(b"^P"), "local mode sent a non-poll command"
                command = payload[5:-3].decode("ascii")
                self.commands.append(command)
                response = self._response(header.device_address, command)
                writer.write(
                    encode_header(
                        header.transaction_id,
                        header.device_code,
                        HEADER_SIZE + len(response),
                        header.device_address,
                        FC_FORWARD_TO_DEVICE,
                    )
                    + response
                )
            await writer.drain()

    def _response(self, address: int, command: str) -> bytes:
        if address > 1:
            return build_p17_response("N")
        responses = {
            "PI": "17",
            "ID": "08ABCD12340000",
            "GMN": "04TEST0000",
            "VFW": "031.0000",
            "PIRI": "2300,100,2300,500,100,5000,4500,480,440,420,460,560,540,2",
            "GS": "2300,500,2295,499,1200,987,42,544,0,12,3,0,88,31,0,0,650,0,3210,0",
            "MOD": "03",
            "GS2": "0,0,0",
            "ET": "12345",
        }
        if self.protocol_id == "18":
            assert command not in {"GMN", "GS2"}
            responses.update(
                {
                    "PI": "18",
                    "ID": "080123450000000000000000",
                    "VFW": "12345,67890,00000",
                    "GS": "2300,500,2295,499,1200,987,42,544,543,542,3,12,88,31,32,33,650,450,3210,3100,0,2,2,1,1,2,1,0",
                }
            )
            data = responses[command]
            content = f"^D{len(data) + 3:03d}{data}".encode("ascii")
            return content + crc_hqx(content, 0).to_bytes(2, "big") + b"\r"
        return build_p17_response("D", responses[command])


class SimulatedSmgCollector:
    """EyeBond collector exposing one SMG/Modbus inverter."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.requests: list[tuple[int, int, int, int, int]] = []
        self.writer: asyncio.StreamWriter | None = None
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Connect to the integration and begin responding."""
        reader, self.writer = await asyncio.open_connection("127.0.0.1", self.port)
        self.task = asyncio.create_task(self._run(reader, self.writer))

    async def stop(self) -> None:
        """Disconnect and stop the response loop."""
        if self.writer is not None:
            self.writer.close()
            with contextlib.suppress(ConnectionError):
                await self.writer.wait_closed()
            self.writer = None
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(
                asyncio.CancelledError, asyncio.IncompleteReadError
            ):
                await self.task
            self.task = None

    async def _run(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            header = decode_header(await reader.readexactly(HEADER_SIZE))
            payload = await reader.readexactly(header.payload_length)
            if header.function_code == FC_HEARTBEAT:
                response = b"PN123456789012"
                writer.write(
                    encode_header(
                        header.transaction_id,
                        1,
                        HEADER_SIZE + len(response),
                        1,
                        FC_HEARTBEAT,
                    )
                    + response
                )
                await writer.drain()
                continue

            assert header.function_code == FC_FORWARD_TO_DEVICE
            assert header.device_code == 1
            assert header.device_address == 0xFF
            assert len(payload) == 8
            assert int.from_bytes(payload[-2:], "little") == crc16_modbus(payload[:-2])
            slave = payload[0]
            function = payload[1]
            register = int.from_bytes(payload[2:4], "big")
            count = int.from_bytes(payload[4:6], "big")
            self.requests.append((slave, function, register, count, header.device_code))
            response = self._response(slave, function, register, count)
            writer.write(
                encode_header(
                    header.transaction_id,
                    header.device_code,
                    HEADER_SIZE + len(response),
                    header.device_address,
                    FC_FORWARD_TO_DEVICE,
                )
                + response
            )
            await writer.drain()

    @staticmethod
    def _response(slave: int, function: int, register: int, count: int) -> bytes:
        assert function == 3, "local SMG mode sent a non-read command"
        if slave != 1:
            return b""
        if register == 201:
            values = [0] * 34
            for address, value in {
                201: 3,
                202: 2301,
                203: 5000,
                210: 2298,
                213: 1180,
                215: 523,
                219: 3205,
                223: 1380,
                225: 19,
                226: 36,
                227: 41,
                229: 82,
                232: 0xFFB4,
            }.items():
                values[address - 201] = value
        elif register == 186:
            raw = b"SMG123456789".ljust(count * 2, b"\x00")
            values = [
                int.from_bytes(raw[index : index + 2], "big")
                for index in range(0, count * 2, 2)
            ]
        elif register == 171:
            values = [0x1E00]
        elif register == 184:
            values = [1]
        elif register == 643:
            values = [6200]
        elif register in (100, 108):
            values = [0, 0]
        else:
            return b""
        assert len(values) == count
        return build_read_holding_response(slave, values)


async def _wait_until(predicate, timeout: float = 3.0) -> None:
    """Wait for an asynchronous state transition without fixed sleeps."""
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.parametrize(
    ("protocol_id", "serial"), [("17", "ABCD1234"), ("18", "01234500")]
)
async def test_local_coordinator_discovers_polls_and_recovers(
    hass: HomeAssistant,
    protocol_id: str,
    serial: str,
) -> None:
    """One code path handles startup, fast data, outage, and reconnection."""
    coordinator = DessMonitorLocalCoordinator(
        hass,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.1",
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
            CONF_LOCAL_DEVICE_CODE: 0,
            CONF_LOCAL_POLL_INTERVAL: 2,
        },
    )
    await coordinator.async_setup()
    first = SimulatedCollector(coordinator._server.listening_port, protocol_id)
    second = SimulatedCollector(coordinator._server.listening_port, protocol_id)
    try:
        await first.start()
        await _wait_until(lambda: bool(coordinator.data))

        assert coordinator.device_code == 2452
        assert set(coordinator.data) == {serial}
        values = {
            point["title"]: point["val"] for point in coordinator.data[serial]["data"]
        }
        assert values["Grid Voltage"] == 230.0
        assert values["Output Active Power"] == 987
        assert values["Battery Charging Current"] == 12
        if protocol_id == "18":
            assert values["PV2 Charger Power"] == 450
            assert values["PV2 Voltage"] == 310.0
        assert values["Data Source"] == "Local"
        assert all(command.isupper() for command in first.commands)

        await first.stop()
        await _wait_until(lambda: not coordinator.last_update_success)

        await second.start()
        await _wait_until(
            lambda: coordinator.last_update_success and "GS" in second.commands
        )
        assert set(coordinator.data) == {serial}
        assert coordinator.data[serial]["data"]
    finally:
        await first.stop()
        await second.stop()
        await coordinator.async_shutdown()


async def test_local_coordinator_auto_detects_read_only_smg(
    hass: HomeAssistant,
) -> None:
    """Cloud devcode 2376 resolves to the distinct SMG tunnel route safely."""
    coordinator = DessMonitorLocalCoordinator(
        hass,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.1",
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
            CONF_LOCAL_DEVICE_CODE: 2376,
            CONF_LOCAL_POLL_INTERVAL: 2,
        },
    )
    await coordinator.async_setup()
    collector = SimulatedSmgCollector(coordinator._server.listening_port)
    try:
        await collector.start()
        await _wait_until(lambda: bool(coordinator.data))

        assert coordinator.device_code == 1
        assert set(coordinator.data) == {"SMG123456789"}
        payload = coordinator.data["SMG123456789"]
        assert payload["device"]["devcode"] == 2376
        assert payload["device"]["local_protocol"] == "smg_modbus"
        assert payload["device"]["local_tunnel_device_code"] == 1
        values = {point["title"]: point["val"] for point in payload["data"]}
        assert values["Grid Voltage"] == 230.1
        assert values["Output Active Power"] == 1180
        assert values["State of Charge"] == 82
        assert values["Battery Current"] == -7.6
        assert {request[1] for request in collector.requests} == {3}
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_partial_inverter_outage_does_not_publish_stale_local_values(
    hass,
) -> None:
    """A healthy neighbour must not keep stale readings above fresh cloud data."""
    coordinator = DessMonitorLocalCoordinator(
        hass,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.1",
        },
    )
    coordinator._identity = CollectorIdentity("TEST-COLLECTOR", "127.0.0.1", 2452)
    coordinator._device_code = 2452
    coordinator._driver = P17Driver()
    coordinator._devices = {
        serial: LocalDevice(
            driver_key="p17",
            transport_device_code=2452,
            collector_address=address,
            device_address=address,
            entity_device_code=2452,
            serial=serial,
            model="TEST",
            firmware="",
            metadata={"PI": "17"},
        )
        for address, serial in [(1, "FIRST"), (2, "SECOND")]
    }
    failed_addresses = set()

    async def send(payload, *, device_code, device_address):
        assert payload.startswith(b"^P")
        if device_address in failed_addresses:
            raise TimeoutError
        command = payload[5:-3].decode("ascii")
        raw = "2300,500,2295,499,1200,987,42,544,0,12,3,0,88,31,0,0,650,0,3210,0"
        return build_p17_response("D", raw if command == "GS" else "03")

    cloud = {
        serial: {
            "collector": {"pn": "TEST-COLLECTOR"},
            "device": {"sn": serial, "devcode": 2452, "devaddr": address},
            "data": [{"title": "Grid Voltage", "val": 220, "unit": "V"}],
        }
        for address, serial in [(1, "FIRST"), (2, "SECOND")]
    }
    with patch.object(coordinator._server, "send_command", side_effect=send):
        assert await coordinator._poll_once(cycle=1)
        assert set(coordinator._coordinator_data()) == {"FIRST", "SECOND"}
        failed_addresses.add(2)
        assert await coordinator._poll_once(cycle=2)
        partial = coordinator._coordinator_data()
        assert set(partial) == {"FIRST"}
        assert set(coordinator._devices) == {"FIRST", "SECOND"}
        merged = merge_cloud_and_local(cloud, partial, local_available=True)
        first = {point["title"]: point["val"] for point in merged["FIRST"]["data"]}
        second = {point["title"]: point["val"] for point in merged["SECOND"]["data"]}
        assert first["Data Source"] == "Local"
        assert first["Grid Voltage"] == 230
        assert second["Data Source"] == "Cloud"
        assert second["Grid Voltage"] == 220

        failed_addresses.clear()
        assert await coordinator._poll_once(cycle=3)
        recovered = coordinator._coordinator_data()
        assert set(recovered) == {"FIRST", "SECOND"}
        assert recovered["SECOND"]["device"]["sn"] == "SECOND"


async def test_failed_poll_cycles_force_targeted_reconnect(
    hass: HomeAssistant,
) -> None:
    """A half-open inverter tunnel is closed after three failed poll cycles."""
    coordinator = DessMonitorLocalCoordinator(
        hass,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.2",
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
            CONF_LOCAL_POLL_INTERVAL: 2,
        },
    )
    coordinator._poll_interval = 0.01
    assert coordinator._announcer.interval == 5.0

    with (
        patch.object(
            type(coordinator._server),
            "connected",
            new_callable=PropertyMock,
            return_value=True,
        ),
        patch.object(
            coordinator, "_poll_once", new=AsyncMock(return_value=False)
        ) as poll_once,
    ):
        with pytest.raises(ConnectionError, match="tunnel became unresponsive"):
            await coordinator._poll_loop()

    assert poll_once.await_count == 3
    assert coordinator.last_update_success is False


async def test_poll_loop_uses_configured_telemetry_interval(
    hass: HomeAssistant,
) -> None:
    """Callback retries never replace the saved telemetry poll interval."""
    coordinator = DessMonitorLocalCoordinator(
        hass,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.2",
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
            CONF_LOCAL_POLL_INTERVAL: 30,
        },
    )
    loop = MagicMock()
    loop.time.side_effect = [0.0, 1.0, 30.0, 31.0]

    with (
        patch.object(
            type(coordinator._server),
            "connected",
            new_callable=PropertyMock,
            side_effect=[True, True, False],
        ),
        patch.object(
            coordinator, "_poll_once", new=AsyncMock(return_value=True)
        ) as poll_once,
        patch(
            "custom_components.dessmonitor.local.coordinator.asyncio.get_running_loop",
            return_value=loop,
        ),
        patch(
            "custom_components.dessmonitor.local.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep,
    ):
        await coordinator._poll_loop()

    assert coordinator._poll_interval == 30
    assert coordinator._announcer.interval == 5.0
    assert poll_once.await_count == 2
    assert sleep.await_args_list == [call(29.0), call(29.0)]
