"""Home Assistant coordinator for local EyeBond collector communication."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..const import (
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_DEVICE_CODE,
    CONF_LOCAL_EXPECTED_PN,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    DEFAULT_LOCAL_DEVICE_CODE,
    DEFAULT_LOCAL_POLL_INTERVAL,
    DEFAULT_LOCAL_TCP_PORT,
    DEFAULT_LOCAL_UDP_PORT,
    DOMAIN,
    SENSOR_TYPES,
)
from .announcer import CollectorAnnouncer
from .drivers import LocalDevice, ReadOnlyLocalDriver, discover_supported_devices
from .protocol import ProtocolError
from .server import CollectorIdentity, CollectorServer

_LOGGER = logging.getLogger(__name__)

_MAX_DEVICE_ADDRESS = 16


class DessMonitorLocalCoordinator(DataUpdateCoordinator):
    """Coordinate local discovery and read-only inverter polling."""

    is_local = True

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
        """Initialize local services without opening sockets."""
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_local", always_update=False)
        self._entry_data = entry_data
        self._poll_interval = int(
            entry_data.get(CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL)
        )
        self._server = CollectorServer(
            host=entry_data[CONF_LOCAL_LISTEN_IP],
            port=int(entry_data.get(CONF_LOCAL_TCP_PORT, DEFAULT_LOCAL_TCP_PORT)),
            allowed_peer_ip=entry_data[CONF_LOCAL_COLLECTOR_IP],
            expected_product_number=entry_data.get(CONF_LOCAL_EXPECTED_PN, ""),
            on_ready=self._async_collector_ready,
            on_disconnect=self._async_collector_disconnected,
        )
        self._announcer = CollectorAnnouncer(
            server_ip=entry_data[CONF_LOCAL_LISTEN_IP],
            server_port=int(
                entry_data.get(CONF_LOCAL_TCP_PORT, DEFAULT_LOCAL_TCP_PORT)
            ),
            collector_ip=entry_data[CONF_LOCAL_COLLECTOR_IP],
            collector_udp_port=int(
                entry_data.get(CONF_LOCAL_UDP_PORT, DEFAULT_LOCAL_UDP_PORT)
            ),
        )
        self._session_task: asyncio.Task[None] | None = None
        self._identity: CollectorIdentity | None = None
        self._device_code: int | None = None
        self._driver: ReadOnlyLocalDriver | None = None
        self._devices: dict[str, LocalDevice] = {}

    @property
    def connected(self) -> bool:
        """Return whether the configured collector is identified."""
        return self._server.connected

    @property
    def device_code(self) -> int | None:
        """Return the discovered transport device code."""
        return self._device_code

    async def async_setup(self) -> None:
        """Start listening before asking the collector to call back."""
        await self._server.start()
        # Port zero is supported by the test/probe boundary; advertise the
        # actual ephemeral listener rather than the pre-bind placeholder.
        self._announcer.server_port = self._server.listening_port
        await self._announcer.start()
        self.async_set_updated_data({})

    async def async_shutdown(self) -> None:
        """Stop all local tasks and sockets."""
        await super().async_shutdown()
        await self._cancel_session()
        await self._announcer.stop()
        await self._server.stop()

    async def async_get_controls_with_values(
        self, _pn: str, _devcode: int, _devaddr: int, _sn: str
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Expose no write controls while local mode is read-only."""
        return {}, {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Return pushed local data when Home Assistant requests a refresh."""
        return self.data or {}

    async def _async_collector_ready(self, identity: CollectorIdentity) -> None:
        """Start a fresh discovery and poll session after identification."""
        await self._cancel_session()
        self._identity = identity
        await self._announcer.stop()
        self._session_task = asyncio.create_task(
            self._run_session(identity), name="dessmonitor_local_session"
        )

    async def _async_collector_disconnected(self) -> None:
        """Mark data unavailable and resume targeted callback requests."""
        current = asyncio.current_task()
        if self._session_task is not current:
            await self._cancel_session()
        self.async_set_update_error(UpdateFailed("Local collector disconnected"))
        await self._announcer.start()

    async def _cancel_session(self) -> None:
        """Cancel and await the active discovery/poll task."""
        task = self._session_task
        self._session_task = None
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run_session(self, identity: CollectorIdentity) -> None:
        """Discover a supported read-only driver and poll until disconnected."""
        try:
            await self._discover(identity)
            await self._poll_loop()
        except asyncio.CancelledError:
            raise
        except ConnectionError:
            await self._server.disconnect()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Local inverter session failed: %s", err)
            self.async_set_update_error(UpdateFailed(str(err)))
            await self._server.disconnect()

    async def _discover(self, identity: CollectorIdentity) -> None:
        """Probe registered read-only drivers and discover unique devices."""
        driver, devices = await discover_supported_devices(
            self._send_command,
            collector_product_number=identity.product_number,
            configured_device_code=int(
                self._entry_data.get(CONF_LOCAL_DEVICE_CODE, DEFAULT_LOCAL_DEVICE_CODE)
            ),
            reported_device_code=identity.reported_device_code,
            max_address=_MAX_DEVICE_ADDRESS,
        )
        self._driver = driver
        self._devices = {device.serial: device for device in devices}
        self._device_code = devices[0].transport_device_code
        _LOGGER.info(
            "Local mode discovered %d inverter(s) using %s (tunnel code %d)",
            len(self._devices),
            driver.key,
            self._device_code,
        )

        successful = await self._poll_once(cycle=0)
        if not successful:
            raise UpdateFailed("Inverter discovery succeeded but status polling failed")
        self.async_set_updated_data(self._coordinator_data())

    async def _poll_loop(self) -> None:
        """Poll fast data continuously and slower data on deterministic cycles."""
        cycle = 1
        failures = 0
        while self._server.connected:
            started = asyncio.get_running_loop().time()
            successful = await self._poll_once(cycle=cycle)

            if successful:
                failures = 0
                self.async_set_updated_data(self._coordinator_data())
            else:
                failures += 1
                if failures >= 3:
                    self.async_set_update_error(
                        UpdateFailed("Local inverter stopped answering status requests")
                    )
                    # A collector can keep its TCP socket half-open after its
                    # inverter tunnel has stopped forwarding. Waiting for the
                    # slower heartbeat watchdog needlessly extends the outage.
                    # Close this exact, peer-pinned route so the disconnect
                    # callback immediately resumes targeted callback requests.
                    raise ConnectionError("local inverter tunnel became unresponsive")

            cycle += 1
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.1, self._poll_interval - elapsed))

    async def _poll_once(self, *, cycle: int) -> bool:
        """Poll all devices through their selected read-only driver."""
        driver = self._driver
        if driver is None:
            raise ConnectionError("local inverter driver has not been discovered")
        successful = False
        for device in self._devices.values():
            try:
                values = await driver.poll(self._send_command, device, cycle=cycle)
            except (TimeoutError, ProtocolError) as err:
                _LOGGER.debug(
                    "Local %s poll failed at address %d: %s",
                    driver.key,
                    device.device_address,
                    err,
                )
                continue
            device.values.update(values)
            successful = True
        return successful

    async def _send_command(
        self, payload: bytes, device_code: int, device_address: int
    ) -> bytes:
        """Adapt the collector server to the shared discovery interface."""
        return await self._server.send_command(
            payload,
            device_code=device_code,
            device_address=device_address,
        )

    def _coordinator_data(self) -> dict[str, Any]:
        """Convert local state to the integration's stable coordinator schema."""
        if self._identity is None or self._device_code is None:
            return {}
        result: dict[str, Any] = {}
        timestamp = datetime.now(timezone.utc).isoformat()
        for device in self._devices.values():
            points = [
                {
                    "title": title,
                    "val": value,
                    "unit": _sensor_unit(title),
                }
                for title, value in sorted(device.values.items())
                if _is_supported_sensor_title(title)
            ]
            points.append({"title": "Timestamp", "val": timestamp, "unit": ""})
            points.append({"title": "Data Source", "val": "Local", "unit": ""})
            result[device.serial] = {
                "collector": {
                    "pn": self._identity.product_number,
                    "ip": self._identity.peer_ip,
                    "fireware": "Local",
                },
                "device": {
                    "sn": device.serial,
                    "alias": f"Local Inverter {device.device_address}",
                    "devcode": device.entity_device_code,
                    "devaddr": device.device_address,
                    "model": device.model,
                    "firmware": device.firmware,
                    "connection_type": "local",
                    "local_protocol": device.driver_key,
                    "local_tunnel_device_code": device.transport_device_code,
                    "local_collector_address": device.collector_address,
                },
                "data": points,
            }
        return result


def _is_supported_sensor_title(title: str) -> bool:
    """Return whether an existing entity definition can represent a local value."""
    if title in SENSOR_TYPES:
        return True
    normalized = title.strip().lower()
    return any(key.strip().lower() == normalized for key in SENSOR_TYPES)


def _sensor_unit(title: str) -> str:
    """Return the existing canonical unit without duplicating HA metadata."""
    config = SENSOR_TYPES.get(title)
    if isinstance(config, dict):
        return str(config.get("unit", ""))
    normalized = title.strip().lower()
    for key, candidate in SENSOR_TYPES.items():
        if key.strip().lower() == normalized and isinstance(candidate, dict):
            return str(candidate.get("unit", ""))
    return ""
