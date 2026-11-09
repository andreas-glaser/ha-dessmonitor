"""Discovery against a collector that stops answering (#53).

A collector whose tunnel goes quiet produced "no supported read-only local
protocol was identified", which reads as missing device support and sent two
reporters down that path. Silence is not evidence about which protocol a
collector speaks, and a driver that already worked for it is.
"""

from __future__ import annotations

from binascii import crc_hqx

import pytest

from custom_components.dessmonitor.local.diagnostics import ProbeDiagnostics
from custom_components.dessmonitor.local.discovery import DiscoveryError
from custom_components.dessmonitor.local.drivers import discover_supported_devices


def _silent():
    """A collector that accepts queries and never answers one."""
    sent: list[str] = []

    async def send(payload: bytes, device_code: int, device_address: int) -> bytes:
        sent.append(f"{device_code}:{device_address}")
        raise TimeoutError("collector did not answer")

    return send, sent


async def _discover(send, diagnostics, **kwargs):
    return await discover_supported_devices(
        send,
        collector_product_number="TEST-PN",
        configured_device_code=2452,
        max_address=1,
        diagnostics=diagnostics,
        **kwargs,
    )


async def test_a_silent_collector_is_not_reported_as_unsupported() -> None:
    send, _ = _silent()
    diagnostics = ProbeDiagnostics()

    with pytest.raises(DiscoveryError) as failure:
        await _discover(send, diagnostics)

    message = str(failure.value)
    assert "did not answer any of" in message
    assert "no supported read-only local protocol" not in message
    assert failure.value.reason == "collector_silent"
    assert diagnostics.silent


async def test_a_driver_that_only_timed_out_is_not_called_invalid() -> None:
    """ProtocolError defaults its reason to invalid_response; a timeout is not one."""
    send, _ = _silent()
    diagnostics = ProbeDiagnostics()

    with pytest.raises(DiscoveryError) as failure:
        await _discover(send, diagnostics)

    assert "p17: timeout" in str(failure.value)
    assert "invalid_response" not in str(failure.value)


async def test_a_known_driver_stops_a_silent_probe_early() -> None:
    """Silence says nothing about the other protocols, so do not pay for them."""
    blind_send, blind_queries = _silent()
    known_send, known_queries = _silent()

    with pytest.raises(DiscoveryError):
        await _discover(blind_send, ProbeDiagnostics())
    with pytest.raises(DiscoveryError) as failure:
        await _discover(known_send, ProbeDiagnostics(), preferred_driver_key="p17")

    assert len(known_queries) < len(blind_queries)
    assert failure.value.reason == "collector_silent"


async def test_a_collector_that_answers_is_still_probed_fully() -> None:
    """An answering collector gives real evidence, so every driver is tried."""

    async def send(*_args: object) -> bytes:
        return b""

    diagnostics = ProbeDiagnostics()
    with pytest.raises(DiscoveryError) as failure:
        await _discover(send, diagnostics, preferred_driver_key="p17")

    assert {attempt.protocol for attempt in diagnostics.attempts} == {
        "p17",
        "smg_modbus",
        "pi30",
    }
    assert failure.value.reason == "discovery_failed"
    assert "answered" in str(failure.value)


async def test_the_remembered_driver_is_tried_first() -> None:
    async def send(*_args: object) -> bytes:
        return b""

    diagnostics = ProbeDiagnostics()
    with pytest.raises(DiscoveryError):
        await _discover(send, diagnostics, preferred_driver_key="pi30")

    assert diagnostics.attempts[0].protocol == "pi30"


async def test_a_driver_with_mixed_outcomes_reports_all_of_them() -> None:
    """A driver that mostly timed out was reported as having answered badly.

    The reporter in #53 saw "smg_modbus: invalid_response; p17: timeout;
    pi30: invalid_response" against 19 timeouts and a single malformed frame.
    Only a driver whose every query timed out escaped the default reason, so
    one stray answer was enough to mislabel ten.
    """
    answered = False

    async def send(payload: bytes, device_code: int, device_address: int) -> bytes:
        nonlocal answered
        if not answered:
            answered = True
            return b"\x00" * 4
        raise TimeoutError("collector did not answer")

    diagnostics = ProbeDiagnostics()
    with pytest.raises(DiscoveryError) as failure:
        await _discover(send, diagnostics)

    message = str(failure.value)
    assert "timeout=" in message
    # Every outcome the probe recorded for a driver is named with its count,
    # so no single query can speak for the rest.
    for driver_key in ("smg_modbus", "p17", "pi30"):
        if f"{driver_key}: " not in message:
            continue
        reported = message.split(f"{driver_key}: ")[1].split(";")[0].split(")")[0]
        counted = sum(
            int(part.split("=")[1]) for part in reported.split(", ") if "=" in part
        )
        assert counted == sum(diagnostics.protocol_outcomes(driver_key).values())


def _pi18_collector(status_outcome: str):
    """A PI18 collector that identifies itself and mishandles GS only.

    ``status_outcome`` is ``"timeout"`` for a status query the inverter never
    answers, or ``"refused"`` for one it rejects.
    """
    identification = {
        "PI": "18",
        "ID": "080123450000000000000000",
        "VFW": "12345,67890,00000",
        "PIRI": (
            "2300,100,2300,500,100,5000,4500,480,440,420,460,560,540,"
            "2,10,060,0,1,2,1,0,0,0,1,2"
        ),
    }
    commands: list[str] = []

    async def send(payload: bytes, _code: int, _address: int) -> bytes:
        command = payload[5:-3].decode("ascii")
        commands.append(command)
        if command in identification:
            data = identification[command]
            content = f"^D{len(data) + 3:03d}{data}".encode("ascii")
            return content + crc_hqx(content, 0).to_bytes(2, "big") + b"\r"
        if command == "GS" and status_outcome == "timeout":
            raise TimeoutError("inverter did not answer the status query")
        return b"^0\x8b\xa6\r"

    return send, commands


async def test_a_status_timeout_keeps_the_identified_p17_inverter() -> None:
    """One unanswered GS discarded an inverter that had just identified itself.

    The reporter in #53 saw "no supported read-only local protocol was
    identified (p17: success=9, timeout=1, ...)" on a collector whose PI, ID,
    VFW and PIRI had all parsed. The driver was rejected for the status query
    alone, which then cost the other two drivers' timeouts - 115 seconds with
    no local telemetry - before the next attempt succeeded unchanged.
    """
    send, commands = _pi18_collector("timeout")
    diagnostics = ProbeDiagnostics()

    driver, (device,) = await _discover(send, diagnostics)

    assert driver.key == "p17"
    assert device.serial == "01234500"
    assert device.values == {}
    assert {attempt.protocol for attempt in diagnostics.attempts} == {"p17"}
    assert "GS" in commands


async def test_a_refused_status_query_still_rejects_p17() -> None:
    """A refusal is evidence about the protocol where a timeout is not."""
    send, _ = _pi18_collector("refused")

    with pytest.raises(DiscoveryError):
        await _discover(send, ProbeDiagnostics())
