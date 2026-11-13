"""Local setting writes, finished only when the inverter reports the new value.

A cloud write is accepted by the platform and may never reach the inverter, so
this integration has always said that an accepted write is not proof that the
setting moved. Over the local link that proof is available: the inverter
acknowledges the command, and its rating reply then carries the value. This
module is the one place that sequence lives.

    read the ratings  ->  encode the command  ->  send it  ->  require the
    acknowledgement  ->  read the ratings again  ->  compare

Nothing is cached as written until the comparison agrees, including after a
request timeout: a timed-out setter may still have been delivered, so the
ratings are re-read to find out rather than the command being sent twice.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .diagnostics import record_query
from .protocol import (
    ProtocolError,
    build_p17_poll,
    build_p17_setter,
    build_pi30_poll,
    build_pi30_setter,
    parse_p17_response,
)
from .settings import LocalSetting, SettingNotWritable, template_for

_LOGGER = logging.getLogger(__name__)

# How long to give an inverter that acknowledged a command before its rating
# reply is read for the second time. Observed acknowledgements are immediate;
# this covers a device that stores the value before it reports it.
_SETTLE_SECONDS = 1.0

# Write outcomes kept per device for the diagnostics download.
MAX_WRITE_HISTORY = 20


class SettingsUnavailable(ProtocolError):
    """Raised when an inverter's settings could not be read back."""


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    """What one inverter reports about its own writable settings."""

    settings: tuple[LocalSetting, ...]
    values: dict[str, str]
    enumerations: dict[str, tuple[str, ...]]
    unreported: tuple[str, ...]

    def setting(self, key: str) -> LocalSetting | None:
        """Return one declared setting by its control id."""
        return next((item for item in self.settings if item.key == key), None)

    def template(self) -> tuple[dict[str, Any], dict[str, str]]:
        """Return the cloud-shaped control template for this inverter."""
        return template_for(self.settings, self.values, self.enumerations)


@dataclass(slots=True)
class WriteOutcome:
    """One attempted write, as the diagnostics download reports it."""

    key: str
    command: str
    requested: str
    acknowledged: bool = False
    verified: bool = False
    reported: str | None = None
    error: str | None = None
    elapsed_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-ready evidence for the diagnostics download."""
        return {
            "setting": self.key,
            # The vendor command name, without the value it carried.
            "command": self.command,
            "requested": self.requested,
            "acknowledged": self.acknowledged,
            "verified": self.verified,
            "reported": self.reported,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


class SettingsBackend:
    """Read and write one ASCII protocol's settings, proving each write.

    Subclasses supply only the protocol's framing and tables; the sequence
    above is shared so neither protocol can drift away from verifying.
    """

    protocol: str
    rating_command: str
    separator: str
    enumeration_queries: tuple[str, ...] = ()

    def settings_for(self, rating_fields: tuple[str, ...]) -> tuple[LocalSetting, ...]:
        """Return the declared settings for this inverter's ratings."""
        raise NotImplementedError

    def parse_enumeration(self, command: str, data: str) -> tuple[str, ...]:
        """Return the values an inverter says it accepts for one setting."""
        raise NotImplementedError

    async def _read(self, send: Any, device: Any, command: str) -> str:
        """Return one reply's data, or raise."""
        raise NotImplementedError

    async def _write(self, send: Any, device: Any, command_text: str) -> bool:
        """Send one setter and return whether the inverter acknowledged it."""
        raise NotImplementedError

    async def async_read(
        self,
        send: Any,
        device: Any,
        known_enumerations: Mapping[str, tuple[str, ...]] | None = None,
    ) -> SettingsSnapshot:
        """Read every setting this inverter reports a value for.

        ``known_enumerations`` are lists of accepted values already read from
        this inverter. They are a property of the model rather than of its
        current state, so re-reading them costs frames on a link that carries
        one transaction at a time and tells us nothing new. A write passes
        them, which is what keeps it to three frames rather than ten.
        """
        data = await self._read(send, device, self.rating_command)
        fields = tuple(value.strip() for value in data.split(self.separator))
        settings = self.settings_for(fields)

        enumerations: dict[str, tuple[str, ...]] = dict(known_enumerations or {})
        for command in self.enumeration_queries:
            if command in enumerations:
                continue
            if not any(item.options_from == command for item in settings):
                continue
            try:
                offered = self.parse_enumeration(
                    command, await self._read(send, device, command)
                )
            except (TimeoutError, ProtocolError, ValueError) as err:
                # Without the list, nothing is offered for the settings that
                # depend on it; the rest are unaffected.
                _LOGGER.debug(
                    "Local %s did not enumerate %s: %s", self.protocol, command, err
                )
                continue
            enumerations[command] = offered

        values: dict[str, str] = {}
        unreported: list[str] = []
        for setting in settings:
            reported = (
                setting.decode(fields[setting.index], enumerations)
                if setting.index < len(fields)
                else None
            )
            if reported is None:
                unreported.append(setting.key)
                continue
            values[setting.key] = reported
        if not values:
            raise SettingsUnavailable(
                f"{self.rating_command} carried no recognisable setting value",
                reason="settings_unavailable",
            )
        return SettingsSnapshot(settings, values, enumerations, tuple(unreported))

    async def async_write(
        self,
        send: Any,
        device: Any,
        key: str,
        value: str,
        enumerations: Mapping[str, tuple[str, ...]] | None = None,
    ) -> tuple[WriteOutcome, SettingsSnapshot]:
        """Write one setting and return the proof, or raise before sending.

        The snapshot returned is a fresh read-back, so a caller publishes what
        the inverter reports rather than what it was asked for.
        """
        started = time.monotonic()
        # Read first: a composite command has to carry its partner's current
        # value, and the owner may have changed it on the inverter's panel
        # since the last poll.
        snapshot = await self.async_read(send, device, enumerations)
        setting = snapshot.setting(key)
        if setting is None:
            raise SettingNotWritable(
                f"{key} is not a setting this inverter reports over the local link"
            )
        if key not in snapshot.values:
            raise SettingNotWritable(
                f"{setting.name} is not reported by this inverter, so a write to "
                "it could not be verified"
            )
        command_text = setting.command_for(
            value, snapshot.values, snapshot.enumerations
        )
        accepted = setting.accept(value, snapshot.enumerations)
        outcome = WriteOutcome(key=key, command=setting.command, requested=accepted)

        try:
            outcome.acknowledged = await self._write(send, device, command_text)
        except TimeoutError:
            # The collector forwards one transaction at a time and answers
            # late often enough to matter (#53). The command may well have
            # been delivered, so the question is answered by reading the
            # setting, never by sending it a second time.
            outcome.error = "the inverter did not acknowledge the command in time"
        except ProtocolError as err:
            outcome.error = str(err)

        verified = await self._verify(
            send, device, setting, accepted, snapshot.enumerations
        )
        outcome.reported = verified.values.get(key)
        outcome.verified = outcome.reported is not None and _same_value(
            outcome.reported, accepted
        )
        outcome.elapsed_ms = round((time.monotonic() - started) * 1000)
        if not outcome.verified and outcome.error is None:
            if not outcome.acknowledged:
                outcome.error = "the inverter refused the command"
            elif outcome.reported is None:
                # Acknowledged, and the setting is no longer among the ones it
                # reports a usable value for. Whatever happened, it is not the
                # change that was asked for.
                outcome.error = (
                    "the inverter acknowledged the command but no longer "
                    "reports this setting"
                )
            else:
                outcome.error = (
                    "the inverter acknowledged the command but still reports "
                    f"{outcome.reported!r}"
                )
        return outcome, verified

    async def _verify(
        self,
        send: Any,
        device: Any,
        setting: LocalSetting,
        accepted: str,
        enumerations: Mapping[str, tuple[str, ...]],
    ) -> SettingsSnapshot:
        """Re-read the settings, allowing one settling delay."""
        snapshot = await self.async_read(send, device, enumerations)
        current = snapshot.values.get(setting.key)
        if current is not None and _same_value(current, accepted):
            return snapshot
        await asyncio.sleep(_SETTLE_SECONDS)
        return await self.async_read(send, device, enumerations)


def _same_value(reported: str, requested: str) -> bool:
    """Compare a reported setting with what was written, as numbers if both are."""
    try:
        return float(reported) == float(requested)
    except (TypeError, ValueError):
        return reported.strip().casefold() == requested.strip().casefold()


class Pi30SettingsBackend(SettingsBackend):
    """PI30 settings, read from ``QPIRI`` and written with named commands."""

    protocol = "pi30"
    rating_command = "QPIRI"
    separator = " "

    def __init__(self) -> None:
        """Bind the PI30 tables without importing them at module scope."""
        from . import pi30_settings

        self._tables = pi30_settings
        self.enumeration_queries = pi30_settings.ENUMERATION_QUERIES

    def settings_for(self, rating_fields: tuple[str, ...]) -> tuple[LocalSetting, ...]:
        """Return the PI30 settings for these ratings."""
        return self._tables.settings_for(rating_fields)

    def parse_enumeration(self, command: str, data: str) -> tuple[str, ...]:
        """Return the accepted values a PI30 inquiry enumerated."""
        return self._tables.parse_enumeration(command, data)

    async def _read(self, send: Any, device: Any, command: str) -> str:
        """Read one PI30 inquiry's data."""
        return await _exchange(
            send,
            device,
            self.protocol,
            command,
            build_pi30_poll(command),
            escape_crc=True,
        )

    async def _write(self, send: Any, device: Any, command_text: str) -> bool:
        """Send one PI30 setter and report the acknowledgement."""
        return await _acknowledged(
            send,
            device,
            self.protocol,
            command_text,
            build_pi30_setter(command_text),
            escape_crc=True,
        )


class P17SettingsBackend(SettingsBackend):
    """PI18/P17 settings, read from ``PIRI`` and written with ``^S`` commands."""

    protocol = "p17"
    rating_command = "PIRI"
    separator = ","

    def __init__(self) -> None:
        """Bind the PI18 tables without importing them at module scope."""
        from . import p17_settings

        self._tables = p17_settings
        self.enumeration_queries = p17_settings.ENUMERATION_QUERIES

    def settings_for(self, rating_fields: tuple[str, ...]) -> tuple[LocalSetting, ...]:
        """Return the PI18 settings for these ratings."""
        return self._tables.settings_for(rating_fields)

    def parse_enumeration(self, command: str, data: str) -> tuple[str, ...]:
        """Return the accepted values a PI18 inquiry enumerated."""
        return self._tables.parse_enumeration(command, data)

    @staticmethod
    def _escape_crc(device: Any) -> bool:
        """PI18 sends the CRC unescaped; P17 stuffs the three reserved bytes."""
        return str(device.metadata.get("PI", "17")) != "18"

    async def _read(self, send: Any, device: Any, command: str) -> str:
        """Read one PI18/P17 inquiry's data."""
        escape_crc = self._escape_crc(device)
        return await _exchange(
            send,
            device,
            self.protocol,
            command,
            build_p17_poll(command, escape_crc=escape_crc),
            escape_crc=escape_crc,
        )

    async def _write(self, send: Any, device: Any, command_text: str) -> bool:
        """Send one PI18/P17 setter and report the acknowledgement."""
        escape_crc = self._escape_crc(device)
        return await _acknowledged(
            send,
            device,
            self.protocol,
            command_text,
            build_p17_setter(command_text, escape_crc=escape_crc),
            escape_crc=escape_crc,
        )


async def _exchange(
    send: Any,
    device: Any,
    protocol: str,
    command: str,
    payload: bytes,
    *,
    escape_crc: bool,
) -> str:
    """Send one framed inquiry and return its validated data."""
    with record_query(
        protocol,
        command,
        device.transport_device_code,
        device.collector_address,
        device.device_address,
    ) as attempt:
        raw = await send(
            payload, device.transport_device_code, device.collector_address
        )
        attempt.response_bytes = len(raw)
        if not raw:
            raise ProtocolError(
                "collector returned an empty inverter response", reason="empty_response"
            )
        response = parse_p17_response(raw, escape_crc=escape_crc)
        if response.response_type != "D":
            raise ProtocolError(
                f"{command} returned an acknowledgement instead of data",
                reason="unexpected_acknowledgement",
            )
        return response.data


async def _acknowledged(
    send: Any,
    device: Any,
    protocol: str,
    command_text: str,
    payload: bytes,
    *,
    escape_crc: bool,
) -> bool:
    """Send one framed setter and return whether it was acknowledged.

    Only the command name is recorded as evidence; the value it carried is
    reported by the write outcome, which the owner downloads themselves.
    """
    name = command_text.split(",")[0].rstrip("0123456789.+-")
    with record_query(
        protocol,
        f"set {name}",
        device.transport_device_code,
        device.collector_address,
        device.device_address,
    ) as attempt:
        raw = await send(
            payload, device.transport_device_code, device.collector_address
        )
        attempt.response_bytes = len(raw)
        if not raw:
            raise ProtocolError(
                "collector returned an empty inverter response", reason="empty_response"
            )
        response = parse_p17_response(raw, escape_crc=escape_crc)
        if response.response_type == "N":
            return False
        if response.response_type != "A":
            raise ProtocolError(
                "inverter answered a setter with data instead of an acknowledgement",
                reason="unexpected_data",
            )
        return True


@dataclass(slots=True)
class WriteHistory:
    """A bounded record of local writes, for the diagnostics download."""

    outcomes: list[dict[str, Any]] = field(default_factory=list)

    def record(self, outcome: WriteOutcome) -> None:
        """Keep the most recent outcomes and drop the oldest."""
        self.outcomes.append(outcome.as_dict())
        del self.outcomes[:-MAX_WRITE_HISTORY]
