"""The write sequence, against an inverter simulated from its own protocol.

The simulator here holds a rating reply and applies setters to it, framing
every answer with independently computed CRCs. That makes these tests evidence
about the sequence the backend performs - read, encode, send, require the
acknowledgement, re-read, compare - rather than about the production framing
helpers agreeing with themselves.
"""

from __future__ import annotations

from binascii import crc_hqx

import pytest

from custom_components.dessmonitor.local.drivers import LocalDevice
from custom_components.dessmonitor.local.settings import SettingNotWritable
from custom_components.dessmonitor.local.writer import (
    P17SettingsBackend,
    Pi30SettingsBackend,
    SettingsUnavailable,
    WriteHistory,
)

PI30_RATINGS = (
    "230.0 21.7 230.0 50.0 21.7 5000 4000 48.0 46.0 42.0 56.4 54.0 0 10 010 "
    "1 0 0 6 01 0 0 54.0 0 1"
).split(" ")
PI18_RATINGS = (
    "2300,217,2300,500,217,5000,5000,480,500,540,450,552,545,2,10,060,1,1,1,"
    "9,1,0,0,0,1,00"
).split(",")

_STUFFED = (0x28, 0x0A, 0x0D)


def _crc(content: bytes, *, escape: bool = True) -> bytes:
    raw = crc_hqx(content, 0).to_bytes(2, "big")
    if not escape:
        return raw
    return bytes(byte + 1 if byte in _STUFFED else byte for byte in raw)


def _device(protocol_id: str = "17") -> LocalDevice:
    return LocalDevice(
        driver_key="test",
        transport_device_code=2452,
        collector_address=1,
        device_address=1,
        entity_device_code=2452,
        serial="SN-TEST",
        model="Test inverter",
        firmware="1.0",
        metadata={"PI": protocol_id},
    )


class Pi30Inverter:
    """A PI30 inverter that answers its own ratings and applies setters.

    The setter decoding below is written from the published command table
    rather than from the integration's own setting table, so a wrong field
    index on either side shows up as a failed verification.
    """

    protocol_id = "30"
    escape_crc = True
    separator = " "
    voltages = {"PBCV": 8, "PSDV": 9, "PCVV": 10, "PBFT": 11, "PBDV": 22}
    codes = {"PBT": 12, "PGR": 15, "POP": 16, "PCP": 17}

    def __init__(self, *, ack: bool = True, apply: bool = True) -> None:
        self.fields = list(PI30_RATINGS)
        self.ack = ack
        self.apply = apply
        self.commands: list[str] = []
        self.timeout_commands: set[str] = set()
        self.offered = "002 010 020 030"

    async def send(self, payload: bytes, _code: int, _address: int) -> bytes:
        text = payload[:-3].decode("ascii")
        self.commands.append(text)
        if text in self.timeout_commands:
            raise TimeoutError(text)
        if text == "QPIRI":
            return self._data(" ".join(self.fields))
        if text == "QMUCHGCR":
            return self._data(self.offered)
        return self._setter(text)

    def _data(self, data: str) -> bytes:
        content = f"({data}".encode("ascii")
        return content + _crc(content) + b"\r"

    def _setter(self, text: str) -> bytes:
        if self.ack and self.apply:
            self._apply(text)
        content = b"(ACK" if self.ack else b"(NAK"
        return content + _crc(content) + b"\r"

    def _apply(self, text: str) -> None:
        for command, index in self.voltages.items():
            if text.startswith(command):
                self.fields[index] = f"{float(text[len(command):]):04.1f}"
                return
        for command, index in self.codes.items():
            if text.startswith(command):
                self.fields[index] = str(int(text[len(command):]))
                return
        if text.startswith("MUCHGC"):
            self.fields[13] = str(int(text[7:], 10))
            return
        if text.startswith("F"):
            self.fields[3] = f"{int(text[1:]):d}.0"
            return
        raise AssertionError(f"unexpected setter {text}")


class Pi18Inverter(Pi30Inverter):
    """A PI18 inverter, with the caret framing and tenths-of-a-volt fields."""

    protocol_id = "18"
    escape_crc = False
    separator = ","

    def __init__(self, *, ack: bool = True, apply: bool = True) -> None:
        super().__init__(ack=ack, apply=apply)
        self.fields = list(PI18_RATINGS)
        self.offered = "010,020,030,040,050,060,070,080"
        self.accepted_ac = "002,010,020,030"

    async def send(self, payload: bytes, _code: int, _address: int) -> bytes:
        assert payload[:2] in (b"^P", b"^S")
        text = payload[5:-3].decode("ascii")
        declared = int(payload[2:5])
        assert declared == len(text) + 3
        self.commands.append(text)
        if text in self.timeout_commands:
            raise TimeoutError(text)
        if payload[:2] == b"^P":
            replies = {
                "PIRI": ",".join(self.fields),
                "MCHGCR": self.offered,
                "MUCHGCR": self.accepted_ac,
            }
            if text not in replies:
                raise AssertionError(f"unexpected inquiry {text}")
            return self._data(replies[text])
        return self._setter(text)

    def _data(self, data: str) -> bytes:
        content = f"^D{len(data) + 3:03d}{data}".encode("ascii")
        return content + _crc(content, escape=False) + b"\r"

    def _setter(self, text: str) -> bytes:
        if self.ack and self.apply:
            self._apply(text)
        marker = b"^1" if self.ack else b"^0"
        return marker + _crc(marker, escape=False) + b"\r"

    def _apply(self, text: str) -> None:
        if text.startswith("MCHGV"):
            bulk, float_voltage = text[5:].split(",")
            self.fields[11], self.fields[12] = bulk, float_voltage
            return
        if text.startswith("BUCD"):
            recharge, redischarge = text[4:].split(",")
            self.fields[8], self.fields[9] = recharge, redischarge
            return
        if text.startswith("PSDV"):
            self.fields[10] = text[4:]
            return
        if text.startswith("MUCHGC"):
            self.fields[14] = text.split(",")[1]
            return
        if text.startswith("MCHGC"):
            self.fields[15] = text.split(",")[1]
            return
        for command, index in (("POP", 17), ("PSP", 23), ("PBT", 13)):
            if text.startswith(command):
                self.fields[index] = text[len(command):]
                return
        if text.startswith("PCP"):
            self.fields[18] = text[4:]
            return
        raise AssertionError(f"unexpected setter {text}")


def _backend(inverter):
    return Pi30SettingsBackend() if inverter.protocol_id == "30" else P17SettingsBackend()


def _fixture(inverter):
    return _backend(inverter), _device(inverter.protocol_id)


PROTOCOLS = [pytest.param(Pi30Inverter, id="pi30"), pytest.param(Pi18Inverter, id="pi18")]


@pytest.fixture(autouse=True)
def _no_settling_delay(monkeypatch) -> None:
    """Keep the settling wait out of the test clock, not out of the sequence."""
    monkeypatch.setattr(
        "custom_components.dessmonitor.local.writer._SETTLE_SECONDS", 0
    )


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_a_read_reports_the_settings_the_inverter_answered_for(
    inverter_class,
) -> None:
    """Only fields the rating reply carried become settings."""
    inverter = inverter_class()
    backend, device = _fixture(inverter)

    snapshot = await backend.async_read(inverter.send, device)

    assert snapshot.values["output_source_priority"]
    assert snapshot.values["battery_bulk_voltage"]
    assert snapshot.setting("battery_bulk_voltage").unit == "V"
    controls, values = snapshot.template()
    # The template is the shape the cloud control API returns, so the entity
    # platforms consume a local device through the path they already use.
    assert controls["Battery Bulk Voltage"]["type"] == "value"
    assert controls["Battery Bulk Voltage"]["id"] == "battery_bulk_voltage"
    assert controls["Output Source Priority"]["type"] == "options"
    assert set(values) == set(snapshot.values)
    assert all(key not in values for key in snapshot.unreported)


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_a_verified_write_is_sent_once_and_reports_the_new_value(
    inverter_class,
) -> None:
    """The write is finished only when the inverter reports the value itself."""
    inverter = inverter_class()
    backend, device = _fixture(inverter)

    outcome, snapshot = await backend.async_write(
        inverter.send, device, "battery_bulk_voltage", "57.0"
    )

    assert outcome.acknowledged is True
    assert outcome.verified is True
    assert outcome.reported == "57.0"
    assert outcome.error is None
    assert snapshot.values["battery_bulk_voltage"] == "57.0"
    setters = [command for command in inverter.commands if not command.startswith(("Q", "PIRI", "MCHGCR", "MUCHGCR"))]
    assert len(setters) == 1
    # The command name only, never the value, is what the probe evidence keeps.
    assert outcome.command in ("PCVV", "MCHGV")


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_a_refused_write_is_reported_as_refused(inverter_class) -> None:
    """A NAK is not a success, and nothing about the setting is claimed."""
    inverter = inverter_class(ack=False)
    backend, device = _fixture(inverter)

    outcome, snapshot = await backend.async_write(
        inverter.send, device, "battery_bulk_voltage", "57.0"
    )

    assert outcome.acknowledged is False
    assert outcome.verified is False
    assert outcome.error == "the inverter refused the command"
    assert snapshot.values["battery_bulk_voltage"] != "57.0"


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_an_acknowledged_write_the_readback_denies_is_not_a_success(
    inverter_class,
) -> None:
    """This is the case a cloud write can never tell an owner about.

    The command was accepted and the setting did not move. Reporting that as
    done is exactly the failure local control exists to remove, so the outcome
    names what the inverter still reports.
    """
    inverter = inverter_class(apply=False)
    backend, device = _fixture(inverter)

    outcome, _ = await backend.async_write(
        inverter.send, device, "battery_bulk_voltage", "57.0"
    )

    assert outcome.acknowledged is True
    assert outcome.verified is False
    assert "still reports" in outcome.error
    assert outcome.reported == ("56.4" if inverter.protocol_id == "30" else "55.2")


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_a_setter_that_times_out_is_never_sent_twice(inverter_class) -> None:
    """A timeout frees this side only; the collector may still deliver it.

    Sending the command again could apply it twice, and on a link that carries
    one transaction at a time it also collides with the reply still coming
    back (#53). The question is answered by reading the setting instead.
    """
    inverter = inverter_class()
    backend, device = _fixture(inverter)
    setter = "PCVV57.0" if inverter.protocol_id == "30" else "MCHGV570,545"
    inverter.timeout_commands.add(setter)

    outcome, _ = await backend.async_write(
        inverter.send, device, "battery_bulk_voltage", "57.0"
    )

    assert inverter.commands.count(setter) == 1
    assert outcome.acknowledged is False
    assert outcome.verified is False
    assert "did not acknowledge" in outcome.error


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_a_setter_that_timed_out_but_landed_is_still_verified(
    inverter_class,
) -> None:
    """What matters is the setting, not the acknowledgement."""
    inverter = inverter_class()
    backend, device = _fixture(inverter)
    setter = "PCVV57.0" if inverter.protocol_id == "30" else "MCHGV570,545"

    async def send(payload, code, address):
        text = (payload[:-3] if inverter.protocol_id == "30" else payload[5:-3]).decode(
            "ascii"
        )
        if text == setter:
            inverter.commands.append(text)
            inverter._apply(text)
            raise TimeoutError(text)
        return await inverter.send(payload, code, address)

    outcome, snapshot = await backend.async_write(
        send, device, "battery_bulk_voltage", "57.0"
    )

    assert inverter.commands.count(setter) == 1
    assert outcome.acknowledged is False
    assert outcome.verified is True
    assert snapshot.values["battery_bulk_voltage"] == "57.0"


async def test_a_composite_write_carries_the_value_the_inverter_reports_now() -> None:
    """The partner's value comes from a read taken during the write.

    ``MCHGV`` writes the bulk and float voltages together. If the float
    voltage were taken from the cached template, a change made on the
    inverter's own panel since the last poll would be written back to what it
    used to be. Here the panel change happens before the write, and the
    command has to carry the new value.
    """
    inverter = Pi18Inverter()
    backend, device = _fixture(inverter)
    stale = await backend.async_read(inverter.send, device)
    assert stale.values["battery_float_voltage"] == "54.5"

    # The owner changes the float voltage on the inverter's panel.
    inverter.fields[12] = "530"
    inverter.commands.clear()

    outcome, snapshot = await backend.async_write(
        inverter.send, device, "battery_bulk_voltage", "57.0", stale.enumerations
    )

    assert "MCHGV570,530" in inverter.commands
    assert outcome.verified is True
    assert snapshot.values["battery_float_voltage"] == "53.0"


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_a_known_enumeration_is_not_read_again(inverter_class) -> None:
    """The list of accepted limits is a property of the model, not its state.

    Re-reading it on every write costs frames on a link that carries one
    transaction at a time, which is time the telemetry poll is not getting.
    """
    inverter = inverter_class()
    backend, device = _fixture(inverter)
    first = await backend.async_read(inverter.send, device)
    assert first.enumerations
    inverter.commands.clear()

    await backend.async_read(inverter.send, device, first.enumerations)

    assert [command for command in inverter.commands if "CHGCR" in command] == []


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_an_unreported_setting_is_refused_before_anything_is_sent(
    inverter_class,
) -> None:
    """A write that could not be verified is not attempted."""
    inverter = inverter_class()
    backend, device = _fixture(inverter)
    inverter.commands.clear()

    with pytest.raises(SettingNotWritable, match="not a setting"):
        await backend.async_write(inverter.send, device, "not_a_setting", "1")

    assert not [
        command
        for command in inverter.commands
        if command not in ("QPIRI", "QMUCHGCR", "PIRI", "MCHGCR", "MUCHGCR")
    ]


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_a_rating_reply_with_nothing_recognisable_is_an_error(
    inverter_class,
) -> None:
    """A reply in an unknown layout is reported, not published field by field.

    Every field is read positionally, so a layout this integration does not
    know would otherwise be published as settings and written back to
    whatever those positions really hold.
    """
    inverter = inverter_class()
    backend, device = _fixture(inverter)
    inverter.fields = ["0"] * 3

    with pytest.raises(SettingsUnavailable):
        await backend.async_read(inverter.send, device)


@pytest.mark.parametrize("inverter_class", PROTOCOLS)
async def test_an_enumerated_limit_writes_the_inverters_own_spelling(
    inverter_class,
) -> None:
    """``QPIRI`` answers 10 where the list offers 010; the list wins."""
    inverter = inverter_class()
    backend, device = _fixture(inverter)
    key = (
        "max_ac_charging_current"
        if inverter.protocol_id == "30"
        else "max_charging_current"
    )

    snapshot = await backend.async_read(inverter.send, device)
    assert snapshot.values[key] in ("010", "060")

    outcome, _ = await backend.async_write(inverter.send, device, key, "020")

    assert outcome.verified is True
    assert outcome.requested == "020"


def test_the_write_history_keeps_the_most_recent_outcomes() -> None:
    """The diagnostics download carries a bounded record, newest last."""
    from custom_components.dessmonitor.local.writer import (
        MAX_WRITE_HISTORY,
        WriteOutcome,
    )

    history = WriteHistory()
    for index in range(MAX_WRITE_HISTORY + 5):
        history.record(
            WriteOutcome(key="battery_bulk_voltage", command="PCVV", requested=str(index))
        )

    assert len(history.outcomes) == MAX_WRITE_HISTORY
    assert history.outcomes[-1]["requested"] == str(MAX_WRITE_HISTORY + 4)
    assert "value" not in history.outcomes[-1]["command"]
