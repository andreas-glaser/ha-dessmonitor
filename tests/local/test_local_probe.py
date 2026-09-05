"""Tests for the contributor-facing read-only local probe."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _load_probe_module() -> ModuleType:
    """Load the standalone tool the same way a contributor executes it."""
    path = Path(__file__).parents[2] / "tools" / "cli" / "local_probe.py"
    spec = importlib.util.spec_from_file_location("dessmonitor_test_local_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_identifiers_are_redacted_by_default() -> None:
    """Reports are shareable without exposing collector or inverter IDs."""
    probe = _load_probe_module()
    redacted = probe._identifier("PRIVATE-SERIAL", include_identifiers=False)
    assert redacted.startswith("sha256:")
    assert "PRIVATE-SERIAL" not in redacted
    assert probe._identifier("PRIVATE-SERIAL", include_identifiers=True) == (
        "PRIVATE-SERIAL"
    )


def test_probe_report_is_private_and_rejects_symlinks(tmp_path: Path) -> None:
    """A local report is mode 0600 and cannot overwrite a symlink target."""
    probe = _load_probe_module()
    report_path = tmp_path / "probe.json"
    probe._write_private_report(report_path, {"safety": "read_only"})
    assert json.loads(report_path.read_text()) == {"safety": "read_only"}
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600

    target = tmp_path / "target.json"
    target.write_text("untouched")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises((OSError, ValueError)):
        probe._write_private_report(link, {"changed": True})
    assert target.read_text() == "untouched"


def test_probe_loads_each_registered_read_only_driver() -> None:
    """The standalone loader sees the same extensible driver registry as HA."""
    probe = _load_probe_module()
    drivers = probe._load_local_module("drivers")
    assert [driver.key for driver in drivers.DRIVERS] == ["p17", "smg_modbus"]


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize(
    ("scenario", "stage", "reason"),
    [
        ("success", "complete", None),
        ("invalid", "discovery", "discovery_failed"),
        ("poll_failure", "polling", "invalid_response"),
        ("silent", "discovery", "timeout"),
        ("no_callback", "collector_callback", "timeout"),
    ],
)
async def test_probe_writes_success_and_failure_reports(
    tmp_path, monkeypatch, scenario, stage, reason
) -> None:
    """Real TCP discovery saves sanitized evidence even when no inverter is found."""
    probe = _load_probe_module()
    protocol = probe._load_local_module("protocol")
    announcer = probe._load_local_module("announcer")
    collector_tasks = []
    status_queries = 0

    async def collector(host, port):
        nonlocal status_queries
        reader, writer = await asyncio.open_connection(host, port)
        try:
            while True:
                try:
                    header = protocol.decode_header(await reader.readexactly(8))
                except asyncio.IncompleteReadError:
                    return
                payload = await reader.readexactly(header.payload_length)
                if header.function_code == protocol.FC_HEARTBEAT:
                    reply = b"PRIVATE-COLLECTOR"
                elif scenario == "silent":
                    continue
                elif scenario == "invalid":
                    reply = b"PRIVATE-RESPONSE"
                else:
                    command = payload[5:-3].decode("ascii")
                    if command == "GS":
                        status_queries += 1
                    if scenario == "poll_failure" and status_queries > 1:
                        reply = b"PRIVATE-POLL-FAILURE"
                    else:
                        values = {
                            "PI": "18",
                            "GS": "2300,500,2300,500,1000,900,20,540,0,10,0,0,80,30,0,0,500,0,3000,0",
                            "MOD": "03",
                            "ET": "00000100",
                        }
                        reply = (
                            protocol.build_p17_response("D", values[command])
                            if command in values
                            else protocol.build_p17_response("N")
                        )
                writer.write(
                    protocol.encode_header(
                        header.transaction_id,
                        2452,
                        8 + len(reply),
                        header.device_address,
                        header.function_code,
                    )
                    + reply
                )
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def request_callback(self):
        if scenario != "no_callback" and not collector_tasks:
            collector_tasks.append(
                asyncio.create_task(collector(self.server_ip, self.server_port))
            )

    # Replace only the outbound UDP request; use the actual server and drivers.
    monkeypatch.setattr(announcer.CollectorAnnouncer, "_send_once", request_callback)
    output = tmp_path / "probe.json"
    args = SimpleNamespace(
        confirm_callback=True,
        listen_ip="127.0.0.1",
        tcp_port=0,
        collector_ip="127.0.0.1",
        expected_product_number="",
        udp_port=58899,
        timeout=0.01 if scenario == "no_callback" else 2,
        probe_timeout=0.1 if scenario == "silent" else 5,
        device_code=2452,
        max_address=1,
        include_identifiers=False,
        output=str(output),
    )
    try:
        if reason is None:
            returned = await probe.run_local_probe(args)
            assert returned["status"] == "success"
            assert returned["diagnostics"]["attempts"]
        else:
            with pytest.raises((protocol.ProtocolError, TimeoutError)):
                await probe.run_local_probe(args)
        report = json.loads(output.read_text())
        assert report["stage"] == stage
        assert report["status"] == ("failed" if reason else "success")
        if reason:
            assert report["error"]["reason"] == reason
        if scenario == "silent":
            assert report["diagnostics"]["outcomes"] == {"cancelled": 1}
        if scenario == "invalid":
            assert report["diagnostics"]["attempts"]
            assert report["inverters"] == []
        assert "PRIVATE" not in output.read_text()
        assert "127.0.0.1" not in output.read_text()
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    finally:
        for task in collector_tasks:
            task.cancel()
        await asyncio.gather(*collector_tasks, return_exceptions=True)
