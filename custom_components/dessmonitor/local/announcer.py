"""Targeted UDP callback requester for EyeBond collectors."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket

from .network import normalize_local_ipv4
from .scanner import build_callback_messages

_LOGGER = logging.getLogger(__name__)


class CollectorAnnouncer:
    """Periodically request a callback from one configured collector."""

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        collector_ip: str,
        collector_udp_port: int,
        *,
        interval: float = 5.0,
        warning_after: float = 120.0,
    ) -> None:
        self.server_ip = normalize_local_ipv4(server_ip)
        if not 0 <= server_port <= 65535:
            raise ValueError("callback TCP port is outside the valid range")
        if not 1 <= collector_udp_port <= 65535:
            raise ValueError("collector UDP port is outside the valid range")
        if interval <= 0 or warning_after <= 0:
            raise ValueError("callback timing must be positive")
        self.server_port = server_port
        self.collector_ip = normalize_local_ipv4(collector_ip)
        self.collector_udp_port = collector_udp_port
        self.interval = interval
        self.warning_after = warning_after
        self._task: asyncio.Task[None] | None = None

    @property
    def payload(self) -> bytes:
        """Return the canonical collector callback command."""
        return self.payloads[0]

    @property
    def payloads(self) -> tuple[bytes, ...]:
        """Return bounded callback variants for firmware compatibility."""
        return build_callback_messages(self.server_ip, self.server_port)

    async def start(self) -> None:
        """Start sending callback requests; repeated calls are harmless."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name="dessmonitor_local_announcer"
            )

    async def stop(self) -> None:
        """Stop redirect announcements."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        """Send a targeted datagram immediately and at the configured interval."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        warning_logged = False
        while True:
            try:
                await self._send_once()
            except asyncio.CancelledError:
                raise
            except OSError as err:
                _LOGGER.debug("Unable to request local collector callback: %s", err)
            if not warning_logged and loop.time() - started >= self.warning_after:
                _LOGGER.warning(
                    "No callback from local collector %s after %.0f seconds. "
                    "Check outbound UDP port %d to the collector and inbound TCP "
                    "access from the collector to %s:%d, including host and VLAN "
                    "firewalls. Do not expose these ports to the internet.",
                    self.collector_ip,
                    self.warning_after,
                    self.collector_udp_port,
                    self.server_ip,
                    self.server_port,
                )
                warning_logged = True
            await asyncio.sleep(self.interval)

    async def _send_once(self) -> None:
        """Send three small compatibility variants using a short-lived socket."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setblocking(False)
            loop = asyncio.get_running_loop()
            for payload in self.payloads:
                await loop.sock_sendto(
                    sock,
                    payload,
                    (self.collector_ip, self.collector_udp_port),
                )
