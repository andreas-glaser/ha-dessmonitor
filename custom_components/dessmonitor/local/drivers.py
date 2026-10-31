"""Small read-only driver boundary for local inverter protocols.

The coordinator owns connection lifecycle and scheduling; drivers own only
protocol detection, validation, and value decoding. New collector/inverter
families can therefore be added without duplicating network or HA logic.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .diagnostics import ProbeDiagnostics, failure_reason
from .discovery import DiscoveryError, discover_p17, query_p17
from .pi30 import discover_pi30, query_pi30
from .profile import CommandNotSupported
from .protocol import P17_DEFAULT_DEVCODE, ProtocolError
from .smg import (
    SMG_CLOUD_DEVICE_CODE,
    SMG_PROTOCOL,
    SMG_REPORTED_COLLECTOR_CODES,
    SmgRoute,
    discover_smg,
    poll_smg,
)
from .smg_protocol4 import PROTOCOL4_CLOUD_DEVICE_CODE

SendCommand = Callable[[bytes, int, int], Awaitable[bytes]]

P17_PROTOCOL = "p17"
_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LocalDevice:
    """Protocol-neutral description and runtime state for one inverter."""

    driver_key: str
    transport_device_code: int
    collector_address: int
    device_address: int
    entity_device_code: int
    serial: str
    model: str
    firmware: str
    metadata: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    disabled_queries: set[str] = field(default_factory=set)
    address_verified: bool = True


class ReadOnlyLocalDriver(Protocol):
    """Interface implemented by every auditable, read-only local driver."""

    key: str

    async def discover(
        self,
        send: SendCommand,
        *,
        collector_product_number: str,
        configured_device_code: int,
        reported_device_code: int,
        max_address: int,
        device_address: int = 0,
    ) -> tuple[LocalDevice, ...]:
        """Return verified devices or raise when this protocol does not match."""

    async def poll(
        self, send: SendCommand, device: LocalDevice, *, cycle: int
    ) -> dict[str, Any]:
        """Return one validated telemetry update."""


class P17Driver:
    """Read-only PI18/P17 ASCII driver."""

    key = P17_PROTOCOL

    async def discover(
        self,
        send: SendCommand,
        *,
        collector_product_number: str,
        configured_device_code: int,
        reported_device_code: int,
        max_address: int,
        device_address: int = 0,
    ) -> tuple[LocalDevice, ...]:
        # 2376 and tunnel code 1 are SMG hints, not P17 tunnel codes.
        p17_configured = (
            0
            if configured_device_code in (1, SMG_CLOUD_DEVICE_CODE)
            else configured_device_code
        )
        p17_reported = 0 if reported_device_code == 1 else reported_device_code
        result = await discover_p17(
            send,
            collector_product_number=collector_product_number,
            configured_device_code=p17_configured,
            reported_device_code=p17_reported,
            max_address=max_address,
            device_address=device_address,
        )
        devices: list[LocalDevice] = []
        for inverter in result.inverters:
            model = str(inverter.metadata.get("GMN", "Local inverter"))
            rated_power = inverter.metadata.get("rated_output_power")
            rated_voltage = inverter.metadata.get("rated_battery_voltage")
            ratings = "/".join(
                part
                for part in (
                    f"{rated_power}W" if rated_power else "",
                    f"{rated_voltage:g}V" if rated_voltage else "",
                )
                if part
            )
            if ratings:
                model = f"{model} ({ratings})"
            device = LocalDevice(
                driver_key=self.key,
                transport_device_code=result.device_code,
                collector_address=inverter.collector_address,
                address_verified=inverter.collector_address != 255,
                device_address=inverter.address,
                entity_device_code=result.device_code,
                serial=inverter.serial,
                model=model,
                firmware=str(inverter.metadata.get("VFW", "")),
                metadata=dict(inverter.metadata),
            )
            device.values.update(await self.poll(send, device, cycle=0))
            devices.append(device)
        return tuple(devices)

    async def poll(
        self, send: SendCommand, device: LocalDevice, *, cycle: int
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        successful_primary = False
        protocol_id = str(device.metadata.get("PI", "17"))
        commands = ["GS", "MOD"]
        if protocol_id == "17" and cycle and cycle % 6 == 0:
            commands.append("GS2")
        if cycle and cycle % 12 == 0:
            commands.append("ET")

        for command in commands:
            if command in device.disabled_queries:
                continue
            try:
                result = await query_p17(
                    send,
                    device.transport_device_code,
                    device.device_address,
                    command,
                    collector_address=device.collector_address,
                    protocol_id=protocol_id,
                )
            except CommandNotSupported:
                device.disabled_queries.add(command)
                continue
            except (TimeoutError, ProtocolError):
                if command == "GS":
                    raise
                continue
            values.update(result)
            successful_primary |= command == "GS"
        if not successful_primary:
            raise ProtocolError("P17 primary status query did not succeed")
        return values


class SmgModbusDriver:
    """Read-only SMG Modbus RTU driver."""

    key = SMG_PROTOCOL

    async def discover(
        self,
        send: SendCommand,
        *,
        collector_product_number: str,
        configured_device_code: int,
        reported_device_code: int,
        max_address: int,
        device_address: int = 0,
    ) -> tuple[LocalDevice, ...]:
        discovered = await discover_smg(
            send,
            collector_product_number=collector_product_number,
            configured_device_code=configured_device_code,
            reported_device_code=reported_device_code,
            max_address=max_address,
            device_address=device_address,
        )
        for item in discovered:
            _LOGGER.info(
                "Local Modbus register layout %d selected at inverter address %d",
                item.route.protocol_number,
                item.route.slave_address,
            )
        return tuple(
            LocalDevice(
                driver_key=self.key,
                transport_device_code=item.route.device_code,
                collector_address=item.route.collector_address,
                device_address=item.route.slave_address,
                entity_device_code=(
                    PROTOCOL4_CLOUD_DEVICE_CODE
                    if item.route.protocol_number == 4
                    else SMG_CLOUD_DEVICE_CODE
                ),
                serial=item.serial,
                model=item.model,
                firmware=item.firmware,
                metadata=dict(item.metadata),
                values=dict(item.initial_values),
            )
            for item in discovered
        )

    async def poll(
        self, send: SendCommand, device: LocalDevice, *, cycle: int
    ) -> dict[str, Any]:
        return await poll_smg(
            send,
            SmgRoute(
                device.transport_device_code,
                device.collector_address,
                device.device_address,
                int(device.metadata.get("layout_code", 0)),
            ),
            include_status=cycle % 6 == 0,
        )


class Pi30Driver:
    """Read-only standard PI30 driver; never selected from a cloud family hint."""

    key = "pi30"

    async def discover(
        self,
        send: SendCommand,
        *,
        collector_product_number: str,
        configured_device_code: int,
        reported_device_code: int,
        max_address: int,
        device_address: int = 0,
    ) -> tuple[LocalDevice, ...]:
        result = await discover_pi30(
            send,
            collector_product_number=collector_product_number,
            configured_device_code=(
                0
                if configured_device_code in (1, SMG_CLOUD_DEVICE_CODE)
                else configured_device_code
            ),
            reported_device_code=(
                0 if reported_device_code == 1 else reported_device_code
            ),
            max_address=max_address,
            device_address=device_address,
        )
        return tuple(
            LocalDevice(
                driver_key=self.key,
                transport_device_code=result.device_code,
                collector_address=item.collector_address,
                device_address=item.address,
                entity_device_code=result.device_code,
                serial=item.serial,
                model="PI30 inverter",
                firmware=str(item.metadata.get("VFW", "")),
                metadata=dict(item.metadata),
                values=dict(item.values),
                address_verified=item.collector_address != 255,
            )
            for item in result.inverters
        )

    async def poll(
        self, send: SendCommand, device: LocalDevice, *, cycle: int
    ) -> dict[str, Any]:
        values = await query_pi30(
            send,
            device.transport_device_code,
            device.collector_address,
            device.device_address,
            "QPIGS",
        )
        if "QMOD" not in device.disabled_queries:
            try:
                values.update(
                    await query_pi30(
                        send,
                        device.transport_device_code,
                        device.collector_address,
                        device.device_address,
                        "QMOD",
                    )
                )
            except CommandNotSupported:
                device.disabled_queries.add("QMOD")
            except (TimeoutError, ProtocolError):
                return values
        return values


DRIVERS: tuple[ReadOnlyLocalDriver, ...] = (
    P17Driver(),
    SmgModbusDriver(),
    Pi30Driver(),
)


async def discover_supported_devices(
    send: SendCommand,
    *,
    collector_product_number: str,
    configured_device_code: int = 0,
    reported_device_code: int = 0,
    max_address: int = 16,
    device_address: int = 0,
    diagnostics: ProbeDiagnostics | None = None,
    preferred_driver_key: str | None = None,
) -> tuple[ReadOnlyLocalDriver, tuple[LocalDevice, ...]]:
    """Try a bounded driver order and return the first verified protocol.

    ``preferred_driver_key`` names a driver that already worked for this
    collector. That is positive evidence about its protocol, so it is tried
    first, and if the collector then answers nothing at all the remaining
    drivers are not probed: silence says nothing about which protocol the
    collector speaks, and every further query costs another request timeout
    while local telemetry is unavailable.
    """
    drivers = list(DRIVERS)
    diagnostics = diagnostics if diagnostics is not None else ProbeDiagnostics()
    if configured_device_code in (1, SMG_CLOUD_DEVICE_CODE) or (
        configured_device_code != P17_DEFAULT_DEVCODE
        and reported_device_code in SMG_REPORTED_COLLECTOR_CODES
    ):
        drivers[0], drivers[1] = drivers[1], drivers[0]
    if preferred_driver_key is not None:
        drivers.sort(key=lambda driver: driver.key != preferred_driver_key)

    failures: list[str] = []
    _LOGGER.debug(
        "Local discovery [%s]: configured code=%d, reported code=%d, driver order=%s",
        diagnostics.probe_id,
        configured_device_code,
        reported_device_code,
        [driver.key for driver in drivers],
    )
    for driver in drivers:
        try:
            with diagnostics.capture():
                devices = await driver.discover(
                    send,
                    collector_product_number=collector_product_number,
                    configured_device_code=configured_device_code,
                    reported_device_code=reported_device_code,
                    max_address=max_address,
                    device_address=device_address,
                )
        except (TimeoutError, ProtocolError, DiscoveryError) as err:
            failures.append(
                f"{driver.key}: {_driver_failure(diagnostics, driver, err)}"
            )
            if driver.key == preferred_driver_key and diagnostics.silent:
                _LOGGER.debug(
                    "Local discovery [%s]: %s answered nothing; not probing the "
                    "remaining drivers",
                    diagnostics.probe_id,
                    driver.key,
                )
                break
            continue
        if devices:
            return driver, devices

    message, reason = _discovery_failure(diagnostics, failures)
    raise DiscoveryError(message, reason=reason)


def _driver_failure(
    diagnostics: ProbeDiagnostics, driver: ReadOnlyLocalDriver, err: BaseException
) -> str:
    """Describe why one driver failed, preferring what the probe observed.

    ``ProtocolError`` defaults its reason to ``invalid_response``, so the
    exception alone reported a malformed frame for a driver whose queries had
    mostly timed out. What the probe recorded is reported instead, in full: a
    driver that timed out nine times and was refused once is not described by
    either outcome on its own.
    """
    outcomes = diagnostics.protocol_outcomes(driver.key)
    if not outcomes:
        return failure_reason(err)
    return ", ".join(
        f"{outcome}={count}" for outcome, count in sorted(outcomes.items())
    )


def _discovery_failure(
    diagnostics: ProbeDiagnostics, failures: list[str]
) -> tuple[str, str]:
    """Return the failure message and reason that the probe actually supports."""
    detail = (
        f"); query outcomes: {diagnostics.summary()}. Enable debug logging for "
        f"per-query diagnostics (probe {diagnostics.probe_id})"
    )
    if diagnostics.silent:
        return (
            f"the collector did not answer any of {diagnostics.attempted} probe "
            "queries, so no read-only local protocol could be identified ("
            + "; ".join(failures)
            + detail,
            "collector_silent",
        )
    return (
        "no supported read-only local protocol was identified ("
        + "; ".join(failures)
        + detail
        + f". The collector answered {diagnostics.answered} of "
        f"{diagnostics.attempted} probe queries",
        "discovery_failed",
    )
