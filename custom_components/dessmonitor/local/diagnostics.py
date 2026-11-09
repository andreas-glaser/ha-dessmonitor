"""Bounded, payload-free evidence for local protocol discovery."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from .profile import CommandNotSupported
from .protocol import ProtocolError

_LOGGER = logging.getLogger(__name__)
MAX_PROBE_ATTEMPTS = 128
_ACTIVE: ContextVar[ProbeDiagnostics | None] = ContextVar(
    "dessmonitor_probe_diagnostics", default=None
)


def failure_reason(error: BaseException) -> str:
    """Classify failures without copying exception text or device payloads."""
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, CommandNotSupported):
        return "unsupported_command"
    if isinstance(error, ProtocolError):
        return error.reason
    if isinstance(error, OSError):
        return "connection_error"
    return "unexpected_error"


@dataclass(slots=True)
class ProbeAttempt:
    """Only command names and numeric routing/validation facts are retained."""

    protocol: str
    command: str
    device_code: int
    collector_address: int
    device_address: int
    response_bytes: int | None = None
    elapsed_ms: int = 0
    outcome: str = "success"
    details: dict[str, int] = field(default_factory=dict)


class ProbeDiagnostics:
    """Collect the first bounded set of attempts in this task's discovery."""

    def __init__(self) -> None:
        self.probe_id = uuid4().hex[:12]
        self.attempts: list[ProbeAttempt] = []
        self.outcomes: Counter[str] = Counter()
        self.dropped_attempts = 0

    @contextmanager
    def capture(self) -> Iterator[None]:
        """Keep simultaneous collector discoveries and ordinary polling separate."""
        token = _ACTIVE.set(self)
        try:
            yield
        finally:
            _ACTIVE.reset(token)

    def record(self, attempt: ProbeAttempt) -> None:
        """Retain bounded evidence, counting attempts beyond the report limit."""
        self.outcomes[attempt.outcome] += 1
        if len(self.attempts) >= MAX_PROBE_ATTEMPTS:
            self.dropped_attempts += 1
            return
        self.attempts.append(attempt)
        _LOGGER.debug("Local probe query [%s]: %s", self.probe_id, asdict(attempt))

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-ready evidence with no payload or exception strings."""
        return {
            "probe_id": self.probe_id,
            "attempts": [asdict(attempt) for attempt in self.attempts],
            "outcomes": dict(self.outcomes),
            "dropped_attempts": self.dropped_attempts,
        }

    @property
    def attempted(self) -> int:
        """Return how many probe queries were issued."""
        return sum(self.outcomes.values())

    @property
    def answered(self) -> int:
        """Return how many probe queries the collector replied to in any form.

        An explicit refusal still counts: it proves the tunnel is carrying
        frames, which a timeout does not.
        """
        return self.attempted - self.outcomes.get("timeout", 0)

    @property
    def silent(self) -> bool:
        """Return whether the collector answered nothing at all."""
        return self.attempted > 0 and self.answered == 0

    def protocol_outcomes(self, protocol: str) -> Counter[str]:
        """Return what one driver's queries actually did.

        Empty while any attempt has been dropped, so a bounded report cannot
        turn a partial view into a confident claim.
        """
        if self.dropped_attempts:
            return Counter()
        return Counter(
            attempt.outcome for attempt in self.attempts if attempt.protocol == protocol
        )

    def summary(self) -> str:
        """Describe observed outcomes even when all protocol drivers fail."""
        return (
            ", ".join(
                f"{reason}={count}" for reason, count in sorted(self.outcomes.items())
            )
            or "no queries completed"
        )


@contextmanager
def record_query(
    protocol: str,
    command: str,
    device_code: int,
    collector_address: int,
    device_address: int,
) -> Iterator[ProbeAttempt]:
    """Observe a query without altering validation, retries, or cancellation."""
    attempt = ProbeAttempt(
        protocol, command, device_code, collector_address, device_address
    )
    started = time.monotonic()
    try:
        yield attempt
    except (Exception, asyncio.CancelledError) as error:
        attempt.outcome = failure_reason(error)
        if isinstance(error, ProtocolError):
            attempt.details.update(error.details)
            if "response_bytes" in error.details:
                attempt.response_bytes = error.details["response_bytes"]
        raise
    finally:
        attempt.elapsed_ms = round((time.monotonic() - started) * 1000)
        diagnostics = _ACTIVE.get()
        if diagnostics is not None:
            diagnostics.record(attempt)
