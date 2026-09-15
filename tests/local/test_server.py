"""Async transport tests with a simulated EyeBond collector."""

from __future__ import annotations

import asyncio
import logging
import socket

import pytest

from custom_components.dessmonitor.local.diagnostics import ProbeDiagnostics
from custom_components.dessmonitor.local.discovery import query_p17
from custom_components.dessmonitor.local.protocol import (
    FC_FORWARD_TO_DEVICE,
    FC_HEARTBEAT,
    HEADER_SIZE,
    ProtocolError,
    decode_header,
    encode_header,
)
from custom_components.dessmonitor.local.server import (
    CollectorIdentity,
    CollectorServer,
)

pytestmark = pytest.mark.usefixtures("socket_enabled")


async def _read_frame(
    reader: asyncio.StreamReader,
) -> tuple[object, bytes]:
    """Read one complete transport frame from the simulated collector side."""
    header = decode_header(await reader.readexactly(HEADER_SIZE))
    payload = await reader.readexactly(header.payload_length)
    return header, payload


async def _identify(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    product_number: bytes = b"PN123456789012",
) -> None:
    """Answer the server's first heartbeat."""
    header, _payload = await _read_frame(reader)
    assert header.function_code == FC_HEARTBEAT
    writer.write(
        encode_header(
            header.transaction_id,
            2452,
            HEADER_SIZE + len(product_number),
            1,
            FC_HEARTBEAT,
        )
        + product_number
    )
    await writer.drain()


async def test_server_round_trip_and_identity() -> None:
    """The pinned collector can identify and complete a matching request."""
    ready = asyncio.Event()
    identities: list[CollectorIdentity] = []

    async def on_ready(identity: CollectorIdentity) -> None:
        identities.append(identity)
        ready.set()

    server = CollectorServer(
        "127.0.0.1",
        0,
        "127.0.0.1",
        heartbeat_interval=30,
        on_ready=on_ready,
    )
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    try:
        await _identify(reader, writer)
        await asyncio.wait_for(ready.wait(), 1)

        request_task = asyncio.create_task(
            server.send_command(b"read-only", device_code=2452, device_address=1)
        )
        header, payload = await _read_frame(reader)
        assert header.function_code == FC_FORWARD_TO_DEVICE
        assert payload == b"read-only"

        response = b"validated response"
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

        assert await request_task == response
        assert identities == [CollectorIdentity("PN123456789012", "127.0.0.1", 2452)]
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


@pytest.mark.parametrize(
    ("payload", "device_code", "address"),
    [(b"READ", 65536, 1), (b"READ", 2452, 256), (b"x" * 4096, 2452, 1)],
    ids=["invalid_code", "invalid_address", "oversized_payload"],
)
async def test_invalid_outbound_frame_does_not_leak_pending_request(
    payload, device_code, address
) -> None:
    """Validation failure must not retain a future that no reply can complete."""
    ready = asyncio.Event()

    async def on_ready(_identity):
        ready.set()

    server = CollectorServer("127.0.0.1", 0, "127.0.0.1", on_ready=on_ready)
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    try:
        await _identify(reader, writer)
        await asyncio.wait_for(ready.wait(), 1)
        with pytest.raises(ProtocolError):
            await server.send_command(
                payload, device_code=device_code, device_address=address
            )
        assert server._connection is not None
        assert not server._connection.pending
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_late_and_unknown_transactions_are_observable_but_never_reused(
    caplog,
) -> None:
    """Late replies cannot satisfy a newer query, and safe headers explain rejection."""
    ready = asyncio.Event()

    async def on_ready(_identity):
        ready.set()

    server = CollectorServer(
        "127.0.0.1", 0, "127.0.0.1", on_ready=on_ready, request_timeout=0.05
    )
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    try:
        await _identify(reader, writer)
        await asyncio.wait_for(ready.wait(), 1)
        caplog.clear()
        caplog.set_level(
            logging.DEBUG, logger="custom_components.dessmonitor.local.server"
        )
        first = asyncio.create_task(
            server.send_command(b"PRIVATE-REQUEST", device_code=2452, device_address=1)
        )
        old_header, _ = await _read_frame(reader)
        with pytest.raises(TimeoutError):
            await first

        second = asyncio.create_task(
            server.send_command(b"PRIVATE-REQUEST", device_code=2452, device_address=1)
        )
        new_header, _ = await _read_frame(reader)
        for transaction_id, response in (
            (old_header.transaction_id, b"PRIVATE-LATE"),
            (65535, b"PRIVATE-UNSOLICITED"),
            (new_header.transaction_id, b"PRIVATE-CURRENT"),
        ):
            writer.write(
                encode_header(
                    transaction_id,
                    2452,
                    HEADER_SIZE + len(response),
                    1,
                    FC_FORWARD_TO_DEVICE,
                )
                + response
            )
        await writer.drain()
        assert await second == b"PRIVATE-CURRENT"
        requests = [
            r for r in caplog.records if r.msg.startswith("Local forward request")
        ]
        replies = [
            r for r in caplog.records if r.msg.startswith("Local forward response")
        ]
        assert len(requests) == 2
        assert len(replies) == 3
        assert len({r.args[0] for r in requests + replies}) == 1
        assert f"transaction_id={old_header.transaction_id}" in replies[0].getMessage()
        assert (
            f"pending_transaction_id={new_header.transaction_id}"
            in replies[0].getMessage()
        )
        assert "outcome=unmatched_transaction" in replies[0].getMessage()
        assert "outcome=unmatched_transaction" in replies[1].getMessage()
        assert "outcome=matched" in replies[2].getMessage()
        assert "PRIVATE" not in caplog.text
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


@pytest.mark.parametrize(("response_code", "response_address"), [(258, 1), (2452, 2)])
async def test_server_rejects_response_metadata_mismatch(
    response_code, response_address
) -> None:
    """A transaction ID alone cannot redirect a response to the wrong request."""
    ready = asyncio.Event()

    async def on_ready(_identity: CollectorIdentity) -> None:
        ready.set()

    server = CollectorServer("127.0.0.1", 0, "127.0.0.1", on_ready=on_ready)
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    try:
        await _identify(reader, writer)
        await asyncio.wait_for(ready.wait(), 1)

        async def send(payload, device_code, address):
            return await server.send_command(
                payload, device_code=device_code, device_address=address
            )

        diagnostics = ProbeDiagnostics()
        with diagnostics.capture():
            request_task = asyncio.create_task(query_p17(send, 2452, 1, "PI"))
        header, _payload = await _read_frame(reader)
        writer.write(
            encode_header(
                header.transaction_id,
                response_code,
                HEADER_SIZE,
                response_address,
                FC_FORWARD_TO_DEVICE,
            )
        )
        await writer.drain()
        with pytest.raises(ProtocolError, match="metadata"):
            await request_task
        attempt = diagnostics.as_dict()["attempts"][0]
        assert attempt["outcome"] == "metadata_mismatch"
        assert attempt["response_bytes"] == 0
        assert attempt["details"] == {
            "expected_device_code": 2452,
            "received_device_code": response_code,
            "expected_device_address": 1,
            "received_device_address": response_address,
            "response_bytes": 0,
        }
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_server_rejects_unconfigured_peer() -> None:
    """Connections from another source address are closed before heartbeats."""
    server = CollectorServer("127.0.0.1", 0, "127.0.0.1")
    await server.start()
    reader, writer = await asyncio.open_connection(
        "127.0.0.1", server.listening_port, local_addr=("127.0.0.2", 0)
    )
    try:
        assert await asyncio.wait_for(reader.read(), 1) == b""
        assert not server.connected
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_server_pins_expected_product_number() -> None:
    """A peer at the right IP still has to match the optional collector ID."""
    server = CollectorServer(
        "127.0.0.1",
        0,
        "127.0.0.1",
        expected_product_number="EXPECTED",
    )
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    try:
        await _identify(reader, writer, product_number=b"SOMETHING-ELSE")
        assert await asyncio.wait_for(reader.read(), 1) == b""
        assert not server.connected
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_server_stop_closes_active_session_before_listener() -> None:
    """Unloading a final listener cannot wait forever on its own connection."""
    ready = asyncio.Event()

    async def on_ready(_identity: CollectorIdentity) -> None:
        ready.set()

    server = CollectorServer("127.0.0.1", 0, "127.0.0.1", on_ready=on_ready)
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    try:
        await _identify(reader, writer)
        await asyncio.wait_for(ready.wait(), 1)
        await asyncio.wait_for(server.stop(), 1)
        assert await asyncio.wait_for(reader.read(), 1) == b""
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_servers_share_listener_and_keep_exact_peer_ownership() -> None:
    """Multiple entries share one port without weakening per-IP routing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])

    first_ready = asyncio.Event()
    second_ready = asyncio.Event()

    async def first_on_ready(_identity: CollectorIdentity) -> None:
        first_ready.set()

    async def second_on_ready(_identity: CollectorIdentity) -> None:
        second_ready.set()

    first = CollectorServer("127.0.0.1", port, "127.0.0.1", on_ready=first_on_ready)
    second = CollectorServer("127.0.0.1", port, "127.0.0.2", on_ready=second_on_ready)
    await first.start()
    await second.start()
    first_reader, first_writer = await asyncio.open_connection(
        "127.0.0.1", port, local_addr=("127.0.0.1", 0)
    )
    second_reader, second_writer = await asyncio.open_connection(
        "127.0.0.1", port, local_addr=("127.0.0.2", 0)
    )
    try:
        await _identify(first_reader, first_writer, product_number=b"FIRST12345678")
        await _identify(second_reader, second_writer, product_number=b"SECOND1234567")
        await asyncio.wait_for(first_ready.wait(), 1)
        await asyncio.wait_for(second_ready.wait(), 1)

        await first.stop()
        request_task = asyncio.create_task(
            second.send_command(b"still-running", device_code=2452, device_address=1)
        )
        header, payload = await _read_frame(second_reader)
        assert payload == b"still-running"
        second_writer.write(
            encode_header(
                header.transaction_id,
                header.device_code,
                HEADER_SIZE,
                header.device_address,
                FC_FORWARD_TO_DEVICE,
            )
        )
        await second_writer.drain()
        assert await request_task == b""
    finally:
        first_writer.close()
        second_writer.close()
        await first_writer.wait_closed()
        await second_writer.wait_closed()
        await first.stop()
        await second.stop()
