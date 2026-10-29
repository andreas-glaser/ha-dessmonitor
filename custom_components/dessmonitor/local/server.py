"""Secure, bounded asyncio server for EyeBond Wi-Fi collectors."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import time
import weakref
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from uuid import uuid4

from .network import normalize_local_ipv4
from .protocol import (
    FC_FORWARD_TO_DEVICE,
    FC_HEARTBEAT,
    HEADER_SIZE,
    EyeBondHeader,
    ProtocolError,
    build_forward_request,
    build_heartbeat_request,
    decode_header,
    parse_heartbeat_response,
)

_LOGGER = logging.getLogger(__name__)

CollectorReadyCallback = Callable[
    ["CollectorIdentity"], Coroutine[object, object, None]
]
CollectorDisconnectCallback = Callable[[], Coroutine[object, object, None]]


class _SharedCollectorListener:
    """One TCP listener routing exact peer IPs to collector owners."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.routes: dict[str, CollectorServer] = {}

    @property
    def listening_port(self) -> int:
        """Return the actual bound port."""
        if self.server is None or not self.server.sockets:
            return self.port
        return int(self.server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        """Open the physical socket once."""
        if self.server is None:
            self.server = await asyncio.start_server(
                self._route_connection,
                host=self.host,
                port=self.port,
                limit=8192,
            )

    async def stop(self) -> None:
        """Close the physical socket."""
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _route_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Route only by a configured exact source IP."""
        peer = writer.get_extra_info("peername")
        peer_ip = str(peer[0]) if isinstance(peer, tuple) and peer else ""
        try:
            normalized_peer = str(ipaddress.ip_address(peer_ip))
        except ValueError:
            normalized_peer = ""
        owner = self.routes.get(normalized_peer)
        if owner is None:
            _LOGGER.warning(
                "Rejected local collector connection from an unconfigured peer"
            )
            await CollectorServer._close_writer(writer)
            return
        await owner._handle_connection(reader, writer)


_LISTENER_POOLS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[tuple[str, int, int], _SharedCollectorListener]
] = weakref.WeakKeyDictionary()
_LISTENER_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


async def _acquire_listener(owner: "CollectorServer") -> _SharedCollectorListener:
    """Register one exact peer route on a process-shared listener."""
    loop = asyncio.get_running_loop()
    lock = _LISTENER_LOCKS.setdefault(loop, asyncio.Lock())
    async with lock:
        pool = _LISTENER_POOLS.setdefault(loop, {})
        # Port zero requests an isolated ephemeral listener for tests/tools.
        key = (owner.host, owner.port, id(owner) if owner.port == 0 else 0)
        listener = pool.get(key)
        if listener is None:
            listener = _SharedCollectorListener(owner.host, owner.port)
            pool[key] = listener
        existing = listener.routes.get(owner.allowed_peer_ip)
        if existing is not None and existing is not owner:
            raise OSError(
                "another local entry already owns this collector IP on the listener"
            )
        listener.routes[owner.allowed_peer_ip] = owner
        try:
            await listener.start()
        except Exception:
            listener.routes.pop(owner.allowed_peer_ip, None)
            if not listener.routes:
                pool.pop(key, None)
            raise
        owner._listener_key = key
        return listener


async def _release_listener(owner: "CollectorServer") -> None:
    """Release one route and close the physical listener when unused."""
    loop = asyncio.get_running_loop()
    lock = _LISTENER_LOCKS.setdefault(loop, asyncio.Lock())
    async with lock:
        pool = _LISTENER_POOLS.get(loop, {})
        key = owner._listener_key
        listener = pool.get(key) if key is not None else None
        owner._listener_key = None
        if listener is None:
            return
        if listener.routes.get(owner.allowed_peer_ip) is owner:
            listener.routes.pop(owner.allowed_peer_ip, None)
        if not listener.routes:
            assert key is not None
            pool.pop(key, None)
            await listener.stop()


@dataclass(frozen=True, slots=True)
class CollectorIdentity:
    """Identity learned from an accepted collector heartbeat."""

    product_number: str
    peer_ip: str
    reported_device_code: int


@dataclass(slots=True)
class PendingRequest:
    """Expected fields for one in-flight RS485 request."""

    future: asyncio.Future[bytes]
    device_code: int
    device_address: int


@dataclass(slots=True)
class CollectorConnection:
    """Mutable state belonging to one collector TCP connection."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    peer_ip: str
    connection_id: str = field(default_factory=lambda: uuid4().hex[:12])
    product_number: str = ""
    started: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    heartbeat_waiters: list[asyncio.Future[None]] = field(default_factory=list)
    ready_notified: bool = False
    closed_locally: bool = False
    pending: dict[int, PendingRequest] = field(default_factory=dict)


class CollectorServer:
    """Manage one pinned EyeBond collector and serialized RS485 requests."""

    def __init__(
        self,
        host: str,
        port: int,
        allowed_peer_ip: str,
        *,
        expected_product_number: str = "",
        heartbeat_interval: float = 60.0,
        request_timeout: float = 3.0,
        on_ready: CollectorReadyCallback | None = None,
        on_disconnect: CollectorDisconnectCallback | None = None,
    ) -> None:
        """Initialize a server without opening sockets."""
        self.host = normalize_local_ipv4(host)
        if not 0 <= port <= 65535:
            raise ValueError("local TCP port is outside the valid range")
        if heartbeat_interval <= 0 or request_timeout <= 0:
            raise ValueError("collector timeouts must be positive")
        self.port = port
        self.allowed_peer_ip = normalize_local_ipv4(allowed_peer_ip)
        self.expected_product_number = expected_product_number.strip()
        self.heartbeat_interval = heartbeat_interval
        self.request_timeout = request_timeout
        self.on_ready = on_ready
        self.on_disconnect = on_disconnect

        self._listener: _SharedCollectorListener | None = None
        self._listener_key: tuple[str, int, int] | None = None
        self._connection: CollectorConnection | None = None
        self._connection_tasks: set[asyncio.Task[None]] = set()
        self._callback_tasks: set[asyncio.Task[None]] = set()
        self._send_lock = asyncio.Lock()
        self._replace_lock = asyncio.Lock()
        self._transaction_id = 0
        self._stopping = False

    @property
    def connected(self) -> bool:
        """Return whether an identified collector is connected."""
        return bool(self._connection and self._connection.ready_notified)

    @property
    def listening_port(self) -> int:
        """Return the actual bound TCP port, including when configured as zero."""
        if self._listener is None:
            return self.port
        return self._listener.listening_port

    async def start(self) -> None:
        """Start accepting collector connections."""
        if self._listener is not None:
            return
        self._stopping = False
        self._listener = await _acquire_listener(self)
        _LOGGER.info(
            "Local collector server listening on %s:%d for peer %s",
            self.host,
            self.listening_port,
            self.allowed_peer_ip,
        )

    async def stop(self) -> None:
        """Stop the server, connection, callbacks, and pending requests."""
        self._stopping = True
        # Python 3.12's Server.wait_closed() waits for active connection
        # handlers. Close this owner's session first so releasing the final
        # shared listener cannot deadlock during unload.
        connection = self._connection
        if connection is not None:
            await self._close_connection(connection, notify=False)

        if self._listener is not None:
            await _release_listener(self)
            self._listener = None

        tasks = tuple(self._connection_tasks | self._callback_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._connection_tasks.clear()
        self._callback_tasks.clear()

    async def send_command(
        self, payload: bytes, *, device_code: int, device_address: int
    ) -> bytes:
        """Send one serialized inverter request and validate response metadata."""
        if not payload:
            raise ProtocolError("refusing to send an empty inverter command")

        async with self._send_lock:
            connection = self._connection
            if connection is None or not connection.ready_notified:
                raise ConnectionError("collector is not connected and identified")

            transaction_id = self._next_transaction_id()
            frame = build_forward_request(
                transaction_id,
                payload,
                device_code,
                device_address,
            )
            loop = asyncio.get_running_loop()
            future: asyncio.Future[bytes] = loop.create_future()
            connection.pending[transaction_id] = PendingRequest(
                future, device_code, device_address
            )

            try:
                async with asyncio.timeout(self.request_timeout):
                    _LOGGER.debug(
                        "Local forward request [%s]: transaction_id=%d, device_code=%d, "
                        "device_address=%d, request_bytes=%d",
                        connection.connection_id,
                        transaction_id,
                        device_code,
                        device_address,
                        len(payload),
                    )
                    connection.writer.write(frame)
                    await connection.writer.drain()
                    return await future
            except TimeoutError:
                _LOGGER.debug(
                    "Local request timed out (device code %d, address %d)",
                    device_code,
                    device_address,
                )
                raise
            finally:
                connection.pending.pop(transaction_id, None)

    async def disconnect(self) -> None:
        """Close the active connection so the collector can establish a clean session."""
        connection = self._connection
        if connection is not None:
            await self._close_connection(connection, notify=not self._stopping)

    async def async_probe_liveness(self, timeout: float | None = None) -> bool:
        """Return whether the collector itself still answers on this connection.

        A silent inverter tunnel and a half-open TCP session both surface as
        request timeouts, and treating the two alike costs a reconnect the
        collector never needed. Its own heartbeat separates them: the collector
        answers that without involving the inverter.
        """
        connection = self._connection
        if connection is None or not connection.ready_notified:
            return False
        # A collector blocked forwarding to its inverter can be slower to
        # answer for itself than an ordinary request, and a false "dead"
        # verdict costs the reconnect this probe exists to avoid, so it is
        # given twice the time one request gets.
        deadline = self.request_timeout * 2 if timeout is None else timeout
        frame = build_heartbeat_request(
            self._next_transaction_id(), max(1, round(self.heartbeat_interval))
        )
        answered: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        connection.heartbeat_waiters.append(answered)
        try:
            connection.writer.write(frame)
            await connection.writer.drain()
            async with asyncio.timeout(deadline):
                await answered
        except (ConnectionError, OSError, TimeoutError):
            return False
        finally:
            with contextlib.suppress(ValueError):
                connection.heartbeat_waiters.remove(answered)
        return self._connection is connection

    def _next_transaction_id(self) -> int:
        """Return a non-zero, wrapping 16-bit transaction identifier."""
        self._transaction_id = self._transaction_id % 0xFFFF + 1
        return self._transaction_id

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Accept the configured peer only and preserve a healthy connection."""
        peer = writer.get_extra_info("peername")
        peer_ip = str(peer[0]) if isinstance(peer, tuple) and peer else ""
        try:
            normalized_peer = str(ipaddress.ip_address(peer_ip))
        except ValueError:
            normalized_peer = ""

        if normalized_peer != self.allowed_peer_ip:
            _LOGGER.warning(
                "Rejected local collector connection from an unconfigured peer"
            )
            await self._close_writer(writer)
            return
        existing = self._connection
        if existing is not None:
            # A second connection usually means the collector abandoned the
            # first, which a half-open socket never reveals on this side. Ask
            # the held session to prove itself before dropping it, so a healthy
            # one is never traded for an unidentified newcomer. One probe at a
            # time: repeated connection attempts must not each cost a frame.
            await self._close_writer(writer)
            async with self._replace_lock:
                if self._connection is not existing:
                    return
                if await self.async_probe_liveness():
                    _LOGGER.warning(
                        "Rejected a second local collector connection; the session "
                        "opened %.0f seconds ago still answers",
                        time.monotonic() - existing.started,
                    )
                    return
                _LOGGER.warning(
                    "The configured local collector opened a second connection and "
                    "the session held for %.0f seconds no longer answers; closing it "
                    "so the collector can call back",
                    time.monotonic() - existing.started,
                )
                await self._close_connection(existing, notify=not self._stopping)
            return

        connection = CollectorConnection(
            reader=reader,
            writer=writer,
            peer_ip=normalized_peer,
        )
        self._connection = connection
        _LOGGER.info("Configured local collector connected")

        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(connection), name="dessmonitor_local_heartbeat"
        )
        watchdog_task = asyncio.create_task(
            self._watchdog_loop(connection), name="dessmonitor_local_watchdog"
        )
        current_task = asyncio.current_task()
        tracked = {heartbeat_task, watchdog_task}
        if current_task is not None:
            tracked.add(current_task)
        self._connection_tasks.update(tracked)

        try:
            await self._read_loop(connection)
        except asyncio.CancelledError:
            raise
        except (ConnectionError, ProtocolError, asyncio.IncompleteReadError) as err:
            lifetime = time.monotonic() - connection.started
            if self._stopping:
                _LOGGER.debug("Local collector connection closed during shutdown")
            elif connection.closed_locally:
                # Closing the socket here raises the same end-of-stream error a
                # collector would. Reporting our own hang-up as a transport
                # failure sent reporters looking at their network (#53).
                _LOGGER.debug(
                    "Local collector connection closed from this side after "
                    "%.0f seconds: %s",
                    lifetime,
                    err,
                )
            elif isinstance(err, asyncio.IncompleteReadError):
                _LOGGER.warning(
                    "The local collector closed its connection after %.0f seconds; "
                    "waiting for it to call back",
                    lifetime,
                )
            else:
                _LOGGER.warning(
                    "Local collector connection closed after %.0f seconds: %s",
                    lifetime,
                    err,
                )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected local collector transport error")
        finally:
            heartbeat_task.cancel()
            watchdog_task.cancel()
            await asyncio.gather(heartbeat_task, watchdog_task, return_exceptions=True)
            self._connection_tasks.difference_update(tracked)
            await self._close_connection(connection, notify=not self._stopping)

    async def _read_loop(self, connection: CollectorConnection) -> None:
        """Read bounded frames and dispatch validated responses."""
        while True:
            header_bytes = await connection.reader.readexactly(HEADER_SIZE)
            header = decode_header(header_bytes)
            payload = await connection.reader.readexactly(header.payload_length)
            if header.function_code == FC_HEARTBEAT:
                await self._handle_heartbeat(connection, header, payload)
            elif header.function_code == FC_FORWARD_TO_DEVICE:
                self._handle_forward_response(connection, header, payload)
            else:
                raise ProtocolError(
                    f"unsupported collector function code {header.function_code}"
                )

    async def _handle_heartbeat(
        self,
        connection: CollectorConnection,
        header: EyeBondHeader,
        payload: bytes,
    ) -> None:
        """Identify and optionally pin the collector product number."""
        product_number = parse_heartbeat_response(payload)
        if (
            self.expected_product_number
            and product_number != self.expected_product_number
        ):
            raise ProtocolError("collector product number does not match configuration")

        connection.last_heartbeat = time.monotonic()
        for waiter in connection.heartbeat_waiters:
            if not waiter.done():
                waiter.set_result(None)
        connection.product_number = product_number
        if connection.ready_notified:
            return
        connection.ready_notified = True
        _LOGGER.info("Local collector identified and ready")
        if self.on_ready is not None:
            self._schedule_callback(
                self.on_ready(
                    CollectorIdentity(
                        product_number=product_number,
                        peer_ip=connection.peer_ip,
                        reported_device_code=header.device_code,
                    )
                ),
                "dessmonitor_local_ready",
            )

    @staticmethod
    def _handle_forward_response(
        connection: CollectorConnection,
        header: EyeBondHeader,
        payload: bytes,
    ) -> None:
        """Resolve only a response that matches the pending request metadata."""
        pending = connection.pending.get(header.transaction_id)
        active_transaction = next(iter(connection.pending), 0)
        if pending is None or pending.future.done():
            outcome = "unmatched_transaction"
        elif (
            header.device_code != pending.device_code
            or header.device_address != pending.device_address
        ):
            outcome = "metadata_mismatch"
        else:
            outcome = "matched"
        _LOGGER.debug(
            "Local forward response [%s]: transaction_id=%d, device_code=%d, "
            "device_address=%d, response_bytes=%d, pending_transaction_id=%d, outcome=%s",
            connection.connection_id,
            header.transaction_id,
            header.device_code,
            header.device_address,
            len(payload),
            active_transaction,
            outcome,
        )
        if pending is None or pending.future.done():
            return
        if outcome == "metadata_mismatch":
            pending.future.set_exception(
                ProtocolError(
                    "collector response metadata does not match its request",
                    reason="metadata_mismatch",
                    details={
                        "expected_device_code": pending.device_code,
                        "received_device_code": header.device_code,
                        "expected_device_address": pending.device_address,
                        "received_device_address": header.device_address,
                        "response_bytes": len(payload),
                    },
                )
            )
            return
        pending.future.set_result(payload)

    async def _heartbeat_loop(self, connection: CollectorConnection) -> None:
        """Send a heartbeat immediately and then at a bounded interval."""
        while self._connection is connection:
            frame = build_heartbeat_request(
                self._next_transaction_id(), max(1, round(self.heartbeat_interval))
            )
            connection.writer.write(frame)
            await connection.writer.drain()
            await asyncio.sleep(self.heartbeat_interval)

    async def _watchdog_loop(self, connection: CollectorConnection) -> None:
        """Close a silent connection so UDP redirection and recovery can resume."""
        while self._connection is connection:
            await asyncio.sleep(min(self.heartbeat_interval, 5.0))
            timeout = (
                max(10.0, self.heartbeat_interval * 2.5)
                if connection.ready_notified
                else 10.0
            )
            if time.monotonic() - connection.last_heartbeat > timeout:
                _LOGGER.warning("Local collector heartbeat timed out")
                await self._close_writer(connection.writer)
                return

    def _schedule_callback(
        self, awaitable: Coroutine[object, object, None], name: str
    ) -> None:
        """Run a lifecycle callback without blocking the transport read loop."""
        task: asyncio.Task[None] = asyncio.create_task(awaitable, name=name)
        self._callback_tasks.add(task)
        task.add_done_callback(self._callback_done)

    def _callback_done(self, task: asyncio.Task[None]) -> None:
        """Consume callback failures so lifecycle errors are visible once."""
        self._callback_tasks.discard(task)
        if task.cancelled():
            return
        exception = task.exception()
        if exception is not None:
            _LOGGER.error("Local collector callback failed: %s", exception)

    async def _close_connection(
        self, connection: CollectorConnection, *, notify: bool
    ) -> None:
        """Close one generation without disturbing a newer connection."""
        was_active = self._connection is connection
        if was_active:
            self._connection = None
        connection.closed_locally = True
        for pending in tuple(connection.pending.values()):
            if not pending.future.done():
                pending.future.set_exception(ConnectionError("collector disconnected"))
        connection.pending.clear()
        for waiter in tuple(connection.heartbeat_waiters):
            if not waiter.done():
                waiter.set_exception(ConnectionError("collector disconnected"))
        connection.heartbeat_waiters.clear()
        await self._close_writer(connection.writer)
        if (
            notify
            and was_active
            and connection.ready_notified
            and self.on_disconnect is not None
        ):
            self._schedule_callback(
                self.on_disconnect(), "dessmonitor_local_disconnected"
            )

    @staticmethod
    async def _close_writer(writer: asyncio.StreamWriter) -> None:
        """Close a stream and suppress platform-specific shutdown errors."""
        writer.close()
        with contextlib.suppress(ConnectionError, OSError, TimeoutError):
            await writer.wait_closed()
