"""Home Assistant coordinator for local Eybond collector communication."""

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
    CONF_LOCAL_CONTROL,
    CONF_LOCAL_DEVICE_ADDRESS,
    CONF_LOCAL_DEVICE_CODE,
    CONF_LOCAL_EXPECTED_PN,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    DEFAULT_LOCAL_CONTROL,
    DEFAULT_LOCAL_DEVICE_ADDRESS,
    DEFAULT_LOCAL_DEVICE_CODE,
    DEFAULT_LOCAL_POLL_INTERVAL,
    DEFAULT_LOCAL_TCP_PORT,
    DEFAULT_LOCAL_UDP_PORT,
    DOMAIN,
    LOCAL_CONTROL_ENABLED,
    LOCAL_SETTINGS_REFRESH_CYCLES,
)
from ..control_values import TRANSPORT_LOCAL, ControlWriteResult
from ..sensor_titles import resolve_sensor_key, sensor_unit
from .announcer import CollectorAnnouncer
from .discovery import inverter_addresses
from .drivers import LocalDevice, LocalDriver, discover_supported_devices
from .protocol import ProtocolError
from .server import CollectorIdentity, CollectorServer
from .settings import SettingNotWritable
from .writer import SettingsSnapshot, WriteHistory

_LOGGER = logging.getLogger(__name__)

_MAX_DEVICE_ADDRESS = 16
# How long a collector that still answers for itself may keep a silent inverter
# tunnel before the session is restarted. Observed silences last tens of
# seconds (#53, #55), so a reconnect inside that window costs local telemetry
# for no gain; one that outlives it may need a fresh discovery.
_SILENT_TUNNEL_GRACE = 180.0
_MAX_RETRY_INTERVAL = 30.0
# Consecutive failed settings reads before an inverter that has never answered
# one drops back to the slow refresh cycle. The first few retries are worth a
# frame each: a collector that has just connected may still be settling. After
# that, asking every poll cycle for the life of the entry would spend one
# transaction in every cycle on a link that carries one at a time, and the
# answer has already been the same three times.
_MAX_SETTINGS_READ_FAILURES = 3


class InverterSilent(Exception):
    """The collector connection is healthy but the inverter answered nothing."""


class DessMonitorLocalCoordinator(DataUpdateCoordinator):
    """Coordinate local discovery and read-only inverter polling."""

    is_local = True

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
        """Initialize local services without opening sockets."""
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_local", always_update=False)
        self._entry_data = entry_data
        self._device_address = entry_data.get(
            CONF_LOCAL_DEVICE_ADDRESS, DEFAULT_LOCAL_DEVICE_ADDRESS
        )
        inverter_addresses(self._device_address, _MAX_DEVICE_ADDRESS)
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
        self._driver: LocalDriver | None = None
        self._devices: dict[str, LocalDevice] = {}
        self._polled_serials: set[str] = set()
        self._silence_started: float | None = None
        self._control_enabled = (
            entry_data.get(CONF_LOCAL_CONTROL, DEFAULT_LOCAL_CONTROL)
            == LOCAL_CONTROL_ENABLED
        )
        self._settings: dict[str, SettingsSnapshot] = {}
        self._settings_errors: dict[str, str] = {}
        self._settings_failures: dict[str, int] = {}
        self._write_history: dict[str, WriteHistory] = {}
        self._control_revision = 0
        self._control_ids: frozenset[str] = frozenset()
        # Serializes a write against the settings read-backs it depends on, so
        # two simultaneous writes cannot each send a composite command built
        # from the state before the other one.
        self._write_lock = asyncio.Lock()
        # Controls are published and written per device, not per field, so one
        # cache keyed the way the cloud coordinator keys its own lets the
        # number and select platforms consume a local device unchanged.
        self.ctrl_value_cache: dict[str, dict[str, Any]] = {}

    @property
    def connected(self) -> bool:
        """Return whether the configured collector is identified."""
        return self._server.connected

    @property
    def cloud_revision(self) -> int:
        """Return the counter entity discovery retries on.

        There is no cloud on a local entry, and the shared loader in
        ``entity_loader.py`` reloads controls only when this advances. A new
        settings read-back that offers a different set of controls is the local
        equivalent of the cloud revision that would have carried them, so that
        is what advances it. Telemetry does not: a push every few seconds would
        otherwise rebuild the control entities for the life of the entry.
        """
        return self._control_revision

    @property
    def driver_key(self) -> str | None:
        """Return the local protocol in use, once one has been identified."""
        return self._driver.key if self._driver is not None else None

    @property
    def control_enabled(self) -> bool:
        """Return whether this entry may write settings over the local link."""
        return self._control_enabled

    def settings_snapshot(self, serial: str) -> SettingsSnapshot | None:
        """Return the last settings read-back for one inverter."""
        return self._settings.get(serial)

    def write_history(self, serial: str) -> list[dict[str, Any]]:
        """Return the recorded outcomes of this inverter's local writes."""
        history = self._write_history.get(serial)
        return list(history.outcomes) if history else []

    def settings_error(self, serial: str) -> str | None:
        """Return why this inverter's settings could not be read, if they were not."""
        return self._settings_errors.get(serial)

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
        _LOGGER.info(
            "Local telemetry route configured for %s with a %d-second polling "
            "interval; requesting callbacks on UDP port %d and accepting the "
            "collector on TCP port %d",
            self._entry_data[CONF_LOCAL_COLLECTOR_IP],
            self._poll_interval,
            self._announcer.collector_udp_port,
            self._server.listening_port,
        )
        await self._announcer.start()
        self.async_set_updated_data({})

    async def async_shutdown(self) -> None:
        """Stop all local tasks and sockets."""
        await super().async_shutdown()
        await self._cancel_session()
        await self._announcer.stop()
        await self._server.stop()

    async def async_get_controls_with_values(
        self, _pn: str, _devcode: int, _devaddr: int, sn: str
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Return the settings this inverter reports, in the cloud's own shape.

        Nothing is offered unless the owner enabled local control, and then
        only settings the inverter reported a value for: a control whose write
        could not be verified is not published at all.
        """
        if not self._control_enabled:
            return {}, {}
        snapshot = self._settings.get(sn)
        if snapshot is None:
            return {}, self.ctrl_value_cache.get(sn, {})
        controls, values = snapshot.template()
        self.ctrl_value_cache.setdefault(sn, {}).update(values)
        return controls, values

    def record_control_write(self, sn: str, field_id: str, value: str) -> None:
        """Cache a verified setting so the entity shows it immediately."""
        if not sn or not field_id:
            return
        self.ctrl_value_cache.setdefault(sn, {})[field_id] = value

    async def async_set_control_value(
        self, sn: str, param_id: str, value: str, *, control_name: str = ""
    ) -> ControlWriteResult:
        """Write one setting over the local link and prove that it moved."""
        if not self._control_enabled:
            raise SettingNotWritable(
                "writing settings over the local link is turned off for this entry"
            )
        driver = self._driver
        device = self._devices.get(sn)
        if driver is None or device is None:
            raise SettingNotWritable(f"{sn} is not a discovered local inverter")
        backend = driver.settings
        if backend is None:
            raise SettingNotWritable(
                f"the {driver.key} protocol has no verifiable setting commands"
            )

        async with self._write_lock:
            known = self._settings[sn].enumerations if sn in self._settings else None
            outcome, snapshot = await backend.async_write(
                self._send_command, device, param_id, value, known
            )
            self._store_settings(sn, snapshot)
            self._write_history.setdefault(sn, WriteHistory()).record(outcome)

        if not outcome.verified:
            _LOGGER.warning(
                "Local write of %s on %s did not take effect: %s",
                control_name or param_id,
                sn,
                outcome.error,
            )
            raise SettingNotWritable(
                f"{control_name or param_id} was not changed: {outcome.error}"
            )
        _LOGGER.info(
            "Local write of %s on %s verified as %s",
            control_name or param_id,
            sn,
            outcome.reported,
        )
        self.record_control_write(sn, param_id, outcome.reported or value)
        self.async_set_updated_data(self._coordinator_data())
        return ControlWriteResult(
            value=outcome.reported or value,
            transport=TRANSPORT_LOCAL,
            verified=True,
        )

    def _store_settings(self, serial: str, snapshot: SettingsSnapshot) -> None:
        """Keep a read-back and advance the control revision when it differs."""
        self._settings[serial] = snapshot
        self._settings_errors.pop(serial, None)
        self._settings_failures.pop(serial, None)
        controls, values = snapshot.template()
        self.ctrl_value_cache.setdefault(serial, {}).update(values)
        offered = frozenset(
            f"{serial}:{config['id']}" for config in controls.values()
        ) | frozenset(
            identifier
            for identifier in self._control_ids
            if not identifier.startswith(f"{serial}:")
        )
        if offered != self._control_ids:
            self._control_ids = offered
            self._control_revision += 1

    async def _refresh_settings(self, *, cycle: int) -> None:
        """Read the settings block on discovery and on its own slow cycle."""
        driver = self._driver
        if not self._control_enabled or driver is None:
            return
        backend = driver.settings
        if backend is None:
            return
        slow_cycle = cycle % LOCAL_SETTINGS_REFRESH_CYCLES == 0
        for serial, device in self._devices.items():
            if serial not in self._polled_serials:
                continue
            if cycle and not slow_cycle:
                # A device whose settings are known is only re-read on the slow
                # cycle. One that has never answered gets a bounded run of
                # immediate retries and then waits for that cycle too.
                if (
                    serial in self._settings
                    or self._settings_failures.get(serial, 0)
                    >= _MAX_SETTINGS_READ_FAILURES
                ):
                    continue
            try:
                known = (
                    self._settings[serial].enumerations
                    if serial in self._settings
                    else None
                )
                snapshot = await backend.async_read(self._send_command, device, known)
            except (TimeoutError, ProtocolError) as err:
                # Telemetry is unaffected: this only means the settings this
                # inverter reports are not known yet, so none are published.
                self._settings_errors[serial] = str(err)
                failures = self._settings_failures.get(serial, 0) + 1
                self._settings_failures[serial] = failures
                if failures == _MAX_SETTINGS_READ_FAILURES:
                    _LOGGER.warning(
                        "Local %s inverter at address %d has not answered %s "
                        "%d times, so it publishes no settings; it is asked "
                        "again every %d polls",
                        driver.key,
                        device.device_address,
                        backend.rating_command,
                        failures,
                        LOCAL_SETTINGS_REFRESH_CYCLES,
                    )
                else:
                    _LOGGER.debug(
                        "Local %s settings read failed at address %d: %s",
                        driver.key,
                        device.device_address,
                        err,
                    )
                continue
            self._store_settings(serial, snapshot)

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
            await self._serve_collector(identity)
        except asyncio.CancelledError:
            raise
        except ConnectionError as err:
            _LOGGER.warning("Restarting the local collector session: %s", err)
            await self._server.disconnect()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Local inverter session failed: %s", err)
            self.async_set_update_error(UpdateFailed(str(err)))
            await self._server.disconnect()

    async def _serve_collector(self, identity: CollectorIdentity) -> None:
        """Discover once, then poll, retrying while the collector answers.

        An inverter that stops answering is not a collector that has gone
        away. Dropping the tunnel for a silence the collector can prove it is
        not responsible for costs a full UDP callback, reconnection and
        rediscovery, and local telemetry is unavailable for all of it (#53).
        """
        self._silence_started = None
        discovered = False
        while True:
            try:
                if not discovered:
                    await self._discover(identity)
                    discovered = True
                await self._poll_loop()
                return
            except InverterSilent as err:
                retry_in = await self._handle_silent_tunnel(err)
                await asyncio.sleep(retry_in)

    async def _handle_silent_tunnel(self, err: Exception) -> float:
        """Keep a proven-alive collector, and return how long to wait.

        Raises ``ConnectionError`` when the collector cannot answer for itself
        or the silence outlives its grace, which restarts the session the way
        every earlier release did.
        """
        if not await self._server.async_probe_liveness():
            raise ConnectionError(
                "the local collector stopped answering its own heartbeat"
            ) from err
        now = asyncio.get_running_loop().time()
        if self._silence_started is None:
            self._silence_started = now
            _LOGGER.warning(
                "%s, while the collector itself still answers. Retrying over the "
                "existing connection for up to %.0f seconds before reconnecting",
                err,
                _SILENT_TUNNEL_GRACE,
            )
        silent_for = now - self._silence_started
        if silent_for >= _SILENT_TUNNEL_GRACE:
            raise ConnectionError(
                f"the inverter answered nothing for {silent_for:.0f} seconds; "
                "reconnecting for a fresh discovery"
            ) from err
        self.async_set_update_error(UpdateFailed(str(err)))
        # Back off with the length of this silence rather than from a counter,
        # so each new silence starts at the configured interval again.
        return min(
            max(1.0, float(self._poll_interval), silent_for), _MAX_RETRY_INTERVAL
        )

    def _note_inverter_answered(self) -> None:
        """Close an open silence window, so the next one starts its own grace."""
        if self._silence_started is None:
            return
        _LOGGER.info(
            "Local inverter resumed answering after %.0f seconds",
            asyncio.get_running_loop().time() - self._silence_started,
        )
        self._silence_started = None

    async def _discover(self, identity: CollectorIdentity) -> None:
        """Probe registered read-only drivers and discover unique devices.

        A collector that drops its tunnel reconnects and rediscovers. Naming
        the driver that last worked keeps a flapping collector from paying for
        a full blind probe on every reconnect, which is time spent with no
        local telemetry at all.
        """
        try:
            driver, devices = await discover_supported_devices(
                self._send_command,
                collector_product_number=identity.product_number,
                configured_device_code=int(
                    self._entry_data.get(
                        CONF_LOCAL_DEVICE_CODE, DEFAULT_LOCAL_DEVICE_CODE
                    )
                ),
                reported_device_code=identity.reported_device_code,
                max_address=_MAX_DEVICE_ADDRESS,
                device_address=self._device_address,
                preferred_driver_key=self._driver.key if self._driver else None,
            )
        except (TimeoutError, ProtocolError) as err:
            raise InverterSilent(str(err)) from err
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
            raise InverterSilent(
                "Inverter discovery succeeded but status polling failed"
            )
        self._note_inverter_answered()
        await self._refresh_settings(cycle=0)
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
                self._note_inverter_answered()
                await self._refresh_settings(cycle=cycle)
                self.async_set_updated_data(self._coordinator_data())
            else:
                failures += 1
                if failures >= 3:
                    # Whether the collector is also gone is decided by its own
                    # heartbeat, not by this silence.
                    raise InverterSilent(
                        "Local inverter stopped answering status requests"
                    )

            cycle += 1
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.1, self._poll_interval - elapsed))

    async def _poll_once(self, *, cycle: int) -> bool:
        """Poll all devices through their selected read-only driver."""
        driver = self._driver
        if driver is None:
            raise ConnectionError("local inverter driver has not been discovered")
        polled_serials: set[str] = set()
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
            polled_serials.add(device.serial)
        self._polled_serials = polled_serials
        return bool(polled_serials)

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
            if device.serial not in self._polled_serials:
                continue
            points = [
                {
                    "title": title,
                    "val": value,
                    "unit": sensor_unit(title),
                }
                for title, value in sorted(device.values.items())
                if resolve_sensor_key(title) is not None
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
                    "local_address_verified": device.address_verified,
                },
                "data": points,
            }
        return result
