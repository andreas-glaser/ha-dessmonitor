"""Observable discovery failures without payload or identifier disclosure."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from custom_components.dessmonitor.local.diagnostics import (
    MAX_PROBE_ATTEMPTS,
    ProbeDiagnostics,
)
from custom_components.dessmonitor.local.discovery import query_p17
from custom_components.dessmonitor.local.drivers import discover_supported_devices
from custom_components.dessmonitor.local.modbus import build_read_holding_response
from custom_components.dessmonitor.local.protocol import (
    ProtocolError,
    build_p17_response,
)
from custom_components.dessmonitor.local.smg import SmgRoute, read_holding_registers


@pytest.mark.parametrize(
    ("response", "outcome"),
    [
        (b"", "empty_response"),
        (build_p17_response("N"), "unsupported_command"),
        (b"^D00518\x00\x00\r", "crc_mismatch"),
        (b"PRIVATE-PAYLOAD", "invalid_response"),
        (TimeoutError("PRIVATE-ADDRESS"), "timeout"),
        (ConnectionError("PRIVATE-ADDRESS"), "connection_error"),
    ],
)
async def test_query_failure_is_classified_and_redacted(
    response, outcome, caplog
) -> None:
    """Distinct failures remain distinct in shareable evidence and debug logs."""

    async def send(*_args):
        if isinstance(response, Exception):
            raise response
        return response

    caplog.set_level(
        logging.DEBUG, logger="custom_components.dessmonitor.local.diagnostics"
    )
    diagnostics = ProbeDiagnostics()
    with diagnostics.capture(), pytest.raises((ProtocolError, OSError)):
        await query_p17(send, 2452, 1, "PI")

    attempt = diagnostics.as_dict()["attempts"][0]
    assert attempt["outcome"] == outcome
    assert attempt["command"] == "PI"
    assert attempt["device_code"] == 2452
    assert attempt["collector_address"] == 1
    assert attempt["elapsed_ms"] >= 0
    assert attempt["response_bytes"] == (
        None if isinstance(response, Exception) else len(response)
    )
    assert outcome in caplog.text
    assert "PRIVATE" not in json.dumps(diagnostics.as_dict()) + caplog.text


async def test_numeric_payload_errors_do_not_escape_into_evidence(caplog) -> None:
    """Parser errors can contain device text; only their classification is retained."""

    async def send(*_args):
        return build_p17_response("D", ",".join(["PRIVATE-VALUE"] * 20))

    caplog.set_level(logging.DEBUG)
    diagnostics = ProbeDiagnostics()
    with diagnostics.capture(), pytest.raises(ProtocolError):
        await query_p17(send, 2452, 1, "GS")
    assert diagnostics.attempts[0].outcome == "invalid_response"
    assert "PRIVATE-VALUE" not in json.dumps(diagnostics.as_dict()) + caplog.text


async def test_discovery_failure_summary_preserves_query_outcomes() -> None:
    """The final error explains what happened even without debug logging enabled."""

    async def send(*_args):
        return b""

    diagnostics = ProbeDiagnostics()
    with pytest.raises(ProtocolError, match="query outcomes: empty_response="):
        await discover_supported_devices(
            send,
            collector_product_number="PRIVATE-PN",
            configured_device_code=2452,
            max_address=1,
            diagnostics=diagnostics,
        )
    assert {attempt.protocol for attempt in diagnostics.attempts} == {
        "p17",
        "smg_modbus",
    }
    assert "PRIVATE-PN" not in json.dumps(diagnostics.as_dict())


@pytest.mark.parametrize(
    ("configured", "reported", "first_protocol"),
    [
        (2452, 258, "p17"),
        (2452, 1, "p17"),
        (0, 258, "smg_modbus"),
        (2376, 2452, "smg_modbus"),
        (1, 2452, "smg_modbus"),
        (0, 2452, "p17"),
        (258, 258, "smg_modbus"),
        (1234, 258, "smg_modbus"),
        (258, 2452, "p17"),
    ],
)
async def test_explicit_device_hint_precedes_collector_hint(
    configured, reported, first_protocol
) -> None:
    """Known P17 hints win; automatic and ambiguous hints retain their ordering."""

    async def send(*_args):
        return b""

    diagnostics = ProbeDiagnostics()
    with pytest.raises(ProtocolError, match="no supported read-only"):
        await discover_supported_devices(
            send,
            collector_product_number="TEST",
            configured_device_code=configured,
            reported_device_code=reported,
            max_address=1,
            diagnostics=diagnostics,
        )
    assert diagnostics.attempts[0].protocol == first_protocol
    assert {attempt.protocol for attempt in diagnostics.attempts} == {
        "p17",
        "smg_modbus",
    }


async def test_modbus_retry_attempts_keep_the_register_route() -> None:
    """A timeout followed by success is visible without changing retry behavior."""
    calls = 0

    async def send(*_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        return build_read_holding_response(1, [2300])

    diagnostics = ProbeDiagnostics()
    with diagnostics.capture():
        assert await read_holding_registers(send, SmgRoute(2452, 255, 1), 202, 1) == (
            2300,
        )
    assert [attempt.outcome for attempt in diagnostics.attempts] == [
        "timeout",
        "success",
    ]
    assert diagnostics.attempts[0].details == {
        "start_register": 202,
        "register_count": 1,
    }


async def test_parallel_captures_are_isolated_and_polling_is_not_retained() -> None:
    """One collector's task cannot contaminate another collector's evidence."""
    first_ready, second_ready = asyncio.Event(), asyncio.Event()
    first, second = ProbeDiagnostics(), ProbeDiagnostics()
    assert first.probe_id != second.probe_id

    async def capture(diagnostics, address, ready, other):
        async def send(*_args):
            ready.set()
            await other.wait()
            return build_p17_response("D", "18")

        with diagnostics.capture():
            await query_p17(send, 2452, address, "PI")
        await query_p17(send, 2452, address, "PI")

    await asyncio.gather(
        capture(first, 1, first_ready, second_ready),
        capture(second, 2, second_ready, first_ready),
    )
    assert [attempt.device_address for attempt in first.attempts] == [1]
    assert [attempt.device_address for attempt in second.attempts] == [2]


async def test_capture_is_bounded_and_cancellation_propagates() -> None:
    """Report size is bounded and cancellation is recorded without being swallowed."""

    async def send(*_args):
        return build_p17_response("D", "18")

    diagnostics = ProbeDiagnostics()
    with diagnostics.capture():
        for _ in range(MAX_PROBE_ATTEMPTS + 3):
            await query_p17(send, 2452, 1, "PI")
    assert len(diagnostics.attempts) == MAX_PROBE_ATTEMPTS
    assert diagnostics.dropped_attempts == 3
    assert diagnostics.outcomes["success"] == MAX_PROBE_ATTEMPTS + 3

    async def cancel(*_args):
        raise asyncio.CancelledError

    cancelled = ProbeDiagnostics()
    with cancelled.capture(), pytest.raises(asyncio.CancelledError):
        await query_p17(cancel, 2452, 1, "PI")
    assert cancelled.attempts[0].outcome == "cancelled"
