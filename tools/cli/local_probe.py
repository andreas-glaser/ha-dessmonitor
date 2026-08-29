"""Read-only local collector probe used to onboard protocol profiles safely."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import json
import logging
import os
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_PACKAGE_NAME = "_dessmonitor_local_probe"
_LOGGER = logging.getLogger(__name__)
_LOCAL_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "dessmonitor"
    / "local"
)


def _load_local_module(name: str) -> ModuleType:
    """Load the integration's pure protocol package without importing HA."""
    if _PACKAGE_NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _PACKAGE_NAME,
            _LOCAL_SOURCE / "__init__.py",
            submodule_search_locations=[str(_LOCAL_SOURCE)],
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load local protocol tools")
        package = importlib.util.module_from_spec(spec)
        sys.modules[_PACKAGE_NAME] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{_PACKAGE_NAME}.{name}")


def _identifier(value: str, include_identifiers: bool) -> str:
    """Redact stable identifiers by default while preserving correlation."""
    if include_identifiers:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


async def run_local_probe(args: Any) -> dict[str, Any]:
    """Redirect one collector temporarily and generate a read-only report."""
    if not args.confirm_callback:
        raise ValueError(
            "refusing to request a collector callback without --confirm-callback"
        )
    announcer_module = _load_local_module("announcer")
    drivers_module = _load_local_module("drivers")
    server_module = _load_local_module("server")

    loop = asyncio.get_running_loop()
    ready: asyncio.Future[Any] = loop.create_future()

    async def on_ready(identity: Any) -> None:
        if not ready.done():
            ready.set_result(identity)

    server = server_module.CollectorServer(
        host=args.listen_ip,
        port=args.tcp_port,
        allowed_peer_ip=args.collector_ip,
        expected_product_number=args.expected_product_number or "",
        on_ready=on_ready,
    )
    announcer = None
    await server.start()
    try:
        announcer = announcer_module.CollectorAnnouncer(
            server_ip=args.listen_ip,
            server_port=server.listening_port,
            collector_ip=args.collector_ip,
            collector_udp_port=args.udp_port,
        )
        await announcer.start()
        try:
            identity = await asyncio.wait_for(ready, timeout=args.timeout)
        except TimeoutError as err:
            raise TimeoutError(
                f"collector {args.collector_ip} did not connect within "
                f"{args.timeout:g} seconds"
            ) from err
        _LOGGER.debug("Collector callback accepted; stopping callback requests")
        await announcer.stop()
        _LOGGER.debug("Starting bounded read-only inverter detection")

        async def send(payload: bytes, device_code: int, address: int) -> bytes:
            return await server.send_command(
                payload,
                device_code=device_code,
                device_address=address,
            )

        try:
            async with asyncio.timeout(args.probe_timeout):
                driver, devices = await drivers_module.discover_supported_devices(
                    send,
                    collector_product_number=identity.product_number,
                    configured_device_code=args.device_code,
                    reported_device_code=identity.reported_device_code,
                    max_address=args.max_address,
                )
                _LOGGER.debug(
                    "Detected local driver %s with %d inverter(s)",
                    driver.key,
                    len(devices),
                )

                inverters: list[dict[str, Any]] = []
                for device in devices:
                    values = await driver.poll(send, device, cycle=12)
                    device.values.update(values)
                    inverters.append(
                        {
                            "address": device.device_address,
                            "serial": _identifier(
                                device.serial, args.include_identifiers
                            ),
                            "model": device.model,
                            "firmware": device.firmware,
                            "sensor_count": len(device.values),
                            "sensors": dict(sorted(device.values.items())),
                        }
                    )
        except TimeoutError as err:
            raise TimeoutError(
                f"read-only inverter detection exceeded {args.probe_timeout:g} seconds"
            ) from err

        report = {
            "report_version": 1,
            "safety": "read_only",
            "collector": {
                "product_number": _identifier(
                    identity.product_number, args.include_identifiers
                ),
                "ip": _identifier(identity.peer_ip, args.include_identifiers),
                "reported_device_code": identity.reported_device_code,
            },
            "detected": {
                "profile": driver.key,
                "tunnel_device_code": devices[0].transport_device_code,
                "collector_address": devices[0].collector_address,
                "inverter_count": len(devices),
            },
            "inverters": inverters,
        }
        if args.output:
            output_path = Path(args.output).expanduser()
            _write_private_report(output_path, report)
        return report
    finally:
        if announcer is not None:
            await announcer.stop()
        await server.stop()


async def run_local_scan(args: Any) -> dict[str, Any]:
    """Run one bounded LAN scan and return validated collector reply sources."""
    if not args.confirm_callback:
        raise ValueError(
            "refusing to request collector callbacks without --confirm-callback"
        )
    scanner_module = _load_local_module("scanner")
    candidates = await scanner_module.scan_collectors(
        bind_ip=args.listen_ip,
        advertised_server_ip=args.listen_ip,
        advertised_server_port=args.tcp_port,
        udp_port=args.udp_port,
        network=args.network or None,
        timeout=args.timeout,
    )
    return {
        "report_version": 1,
        "safety": "bounded_callback_discovery",
        "network": str(
            scanner_module.scan_network_for_host(
                args.listen_ip, args.network or None
            )
        ),
        "candidate_count": len(candidates),
        "candidates": [
            {"ip": candidate.ip, "reply_code": candidate.reply_code}
            for candidate in candidates
        ],
    }


def _write_private_report(path: Path, report: dict[str, Any]) -> None:
    """Write a private report without following a pre-existing symlink."""
    if path.is_symlink():
        raise ValueError("local probe output must not be a symbolic link")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("local probe output must be a regular file")
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as output:
            json.dump(report, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)
