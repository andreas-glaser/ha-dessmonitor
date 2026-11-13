"""Local control through the coordinator, over the real collector transport.

These drive the whole path an owner's click takes: the coordinator reads the
settings its inverter reports, publishes them in the shape the entity
platforms consume, sends a setter over the tunnel, and reports the write only
once the inverter has confirmed it.
"""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dessmonitor.const import (
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_CONTROL,
    CONF_LOCAL_DEVICE_ADDRESS,
    CONF_LOCAL_DEVICE_CODE,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    LOCAL_CONTROL_ENABLED,
)
from custom_components.dessmonitor.control_values import TRANSPORT_LOCAL
from custom_components.dessmonitor.local.coordinator import DessMonitorLocalCoordinator
from custom_components.dessmonitor.local.settings import SettingNotWritable
from tests.local.test_coordinator import SimulatedCollector, _wait_until

pytestmark = pytest.mark.usefixtures("socket_enabled")

SERIAL = "01234500"


def _coordinator(hass: HomeAssistant, *, control: bool) -> DessMonitorLocalCoordinator:
    """Build a local entry with local control on or off."""
    data = {
        CONF_LOCAL_LISTEN_IP: "127.0.0.1",
        CONF_LOCAL_COLLECTOR_IP: "127.0.0.1",
        CONF_LOCAL_TCP_PORT: 0,
        CONF_LOCAL_UDP_PORT: 9,
        CONF_LOCAL_DEVICE_CODE: 0,
        CONF_LOCAL_DEVICE_ADDRESS: 0,
        CONF_LOCAL_POLL_INTERVAL: 2,
    }
    if control:
        data[CONF_LOCAL_CONTROL] = LOCAL_CONTROL_ENABLED
    return DessMonitorLocalCoordinator(hass, data)


async def _started(hass: HomeAssistant, *, control: bool):
    """Return a running coordinator and its connected collector."""
    coordinator = _coordinator(hass, control=control)
    await coordinator.async_setup()
    collector = SimulatedCollector(
        coordinator._server.listening_port, "18", 1, allow_writes=control
    )
    await collector.start()
    await _wait_until(lambda: bool(coordinator.data))
    return coordinator, collector


async def test_a_read_only_entry_asks_the_inverter_for_no_setting(
    hass: HomeAssistant,
) -> None:
    """With local control off, nothing about this changes for an owner.

    Local mode was read-only for its whole life and the option defaults to
    off, so an upgrade must not send one extra frame or publish one extra
    entity. The simulated collector refuses a setter outright, and the rating
    reply is not even asked for outside discovery.
    """
    coordinator, collector = await _started(hass, control=False)
    try:
        assert coordinator.control_enabled is False
        controls, values = await coordinator.async_get_controls_with_values(
            "PN123456789012", 2452, 1, SERIAL
        )
        assert controls == {}
        assert values == {}
        assert coordinator.settings_snapshot(SERIAL) is None

        # PIRI is read once during discovery, for the device's rated power.
        # Nothing re-reads it, and no setter is ever framed.
        await _wait_until(lambda: collector.commands.count("GS") >= 2)
        assert collector.commands.count("PIRI") == 1
        assert not [
            command for command in collector.commands if command.startswith("MCHG")
        ]

        with pytest.raises(SettingNotWritable, match="turned off"):
            await coordinator.async_set_control_value(
                SERIAL, "battery_bulk_voltage", "57.0"
            )
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_an_enabled_entry_publishes_the_settings_its_inverter_reports(
    hass: HomeAssistant,
) -> None:
    """The template is the cloud control template's own shape."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        controls, values = await coordinator.async_get_controls_with_values(
            "PN123456789012", 2452, 1, SERIAL
        )

        assert controls["Battery Bulk Voltage"] == {
            "id": "battery_bulk_voltage",
            "type": "value",
            "unit": "V",
            "hint": "48.0~58.5V",
        }
        assert controls["Output Source Priority"]["type"] == "options"
        assert controls["Max Charging Current"]["options"]["060"] == "60 A"
        assert values["battery_bulk_voltage"] == "56.0"
        assert values["battery_float_voltage"] == "54.0"
        # The value cache is keyed the way the cloud coordinator keys its own,
        # so the number and select platforms need no local-specific branch.
        assert coordinator.ctrl_value_cache[SERIAL]["battery_bulk_voltage"] == "56.0"
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_a_write_is_reported_only_after_the_inverter_confirms_it(
    hass: HomeAssistant,
) -> None:
    """The verified value, not the requested one, is what reaches the entity."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        collector.commands.clear()

        result = await coordinator.async_set_control_value(
            SERIAL, "battery_bulk_voltage", "57.0", control_name="Battery Bulk Voltage"
        )

        assert result.transport == TRANSPORT_LOCAL
        assert result.verified is True
        assert result.value == "57.0"
        assert "MCHGV570,540" in collector.commands
        assert coordinator.ctrl_value_cache[SERIAL]["battery_bulk_voltage"] == "57.0"
        assert coordinator.settings_snapshot(SERIAL).values[
            "battery_bulk_voltage"
        ] == "57.0"
        history = coordinator.write_history(SERIAL)
        assert history[-1]["verified"] is True
        assert history[-1]["setting"] == "battery_bulk_voltage"
        assert history[-1]["command"] == "MCHGV"
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_a_refused_write_raises_and_caches_nothing(hass: HomeAssistant) -> None:
    """An owner is told the setting did not change, and the cache still agrees."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        collector.ack_writes = False

        with pytest.raises(SettingNotWritable, match="was not changed"):
            await coordinator.async_set_control_value(
                SERIAL,
                "battery_bulk_voltage",
                "57.0",
                control_name="Battery Bulk Voltage",
            )

        assert coordinator.ctrl_value_cache[SERIAL]["battery_bulk_voltage"] == "56.0"
        assert coordinator.write_history(SERIAL)[-1]["verified"] is False
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_an_acknowledged_write_that_did_not_take_is_still_a_failure(
    hass: HomeAssistant,
) -> None:
    """Accepting a command is not applying it, and only one of those is a write."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        collector.apply_writes = False

        with pytest.raises(SettingNotWritable, match="still reports"):
            await coordinator.async_set_control_value(
                SERIAL, "battery_bulk_voltage", "57.0"
            )

        assert coordinator.ctrl_value_cache[SERIAL]["battery_bulk_voltage"] == "56.0"
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_settings_are_re_read_on_their_own_slow_cycle(
    hass: HomeAssistant,
) -> None:
    """A setting changed on the inverter's panel appears without a reload.

    Telemetry is polled every few seconds and the settings much more slowly,
    because each read costs frames on a link that carries one transaction at a
    time. The refresh interval is shortened here rather than waited out.
    """
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            "custom_components.dessmonitor.local.coordinator"
            ".LOCAL_SETTINGS_REFRESH_CYCLES",
            1,
        )
        coordinator, collector = await _started(hass, control=True)
        try:
            await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
            # The owner changes the bulk voltage on the inverter's own panel.
            collector.ratings[11] = "575"

            await _wait_until(
                lambda: coordinator.settings_snapshot(SERIAL).values[
                    "battery_bulk_voltage"
                ]
                == "57.5",
                timeout=8.0,
            )
            # The list of accepted limits is a property of the model, so it is
            # read once and not on every refresh.
            assert collector.commands.count("MCHGCR") == 1
        finally:
            await collector.stop()
            await coordinator.async_shutdown()


async def test_a_protocol_with_no_verifiable_setter_refuses_to_write(
    hass: HomeAssistant,
) -> None:
    """SMG/Modbus stays read-only, and says why rather than failing obscurely.

    A Modbus write names a holding register by number, and no vendor register
    map for this inverter family was obtainable. A wrong address is a changed
    setting on someone's hardware, so the driver carries no settings backend
    at all.
    """
    from custom_components.dessmonitor.local.drivers import SmgModbusDriver

    assert SmgModbusDriver().settings is None
    coordinator = _coordinator(hass, control=True)
    coordinator._driver = SmgModbusDriver()
    coordinator._devices = {SERIAL: object()}

    with pytest.raises(SettingNotWritable, match="no verifiable setting commands"):
        await coordinator.async_set_control_value(SERIAL, "battery_bulk_voltage", "57")


async def test_a_write_to_an_undiscovered_device_is_refused(
    hass: HomeAssistant,
) -> None:
    """Nothing is sent for a serial this transport has never seen."""
    coordinator = _coordinator(hass, control=True)

    with pytest.raises(SettingNotWritable, match="not a discovered local inverter"):
        await coordinator.async_set_control_value("UNKNOWN", "battery_bulk_voltage", "57")


async def test_two_writes_cannot_interleave_their_read_backs(
    hass: HomeAssistant,
) -> None:
    """A composite command must not be built from state another write replaced.

    ``MCHGV`` carries the bulk and float voltages together. Two writes running
    at once could each read the ratings before the other sent its setter, and
    the second would then write the first one's value back.
    """
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)

        bulk, float_voltage = await asyncio.gather(
            coordinator.async_set_control_value(
                SERIAL, "battery_bulk_voltage", "58.0"
            ),
            coordinator.async_set_control_value(
                SERIAL, "battery_float_voltage", "53.0"
            ),
        )

        assert bulk.verified and float_voltage.verified
        snapshot = coordinator.settings_snapshot(SERIAL)
        assert snapshot.values["battery_bulk_voltage"] == "58.0"
        assert snapshot.values["battery_float_voltage"] == "53.0"
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_an_inverter_that_never_answers_is_not_asked_every_poll(
    hass: HomeAssistant,
) -> None:
    """A settings read that keeps failing drops back to the slow cycle.

    Telemetry is unaffected either way, but the link carries one transaction at
    a time: asking an inverter that has answered nothing three times on every
    poll for the life of the entry would spend one of those transactions in
    every cycle, for an answer that has not changed.
    """
    from custom_components.dessmonitor.local.coordinator import (
        _MAX_SETTINGS_READ_FAILURES,
    )

    coordinator, collector = await _started(hass, control=True)
    try:
        # The inverter answers telemetry and refuses the rating inquiry, which
        # is what a firmware without it looks like.
        collector.refuse_commands.add("PIRI")
        coordinator._settings.clear()
        coordinator._settings_failures.clear()
        collector.commands.clear()

        await _wait_until(
            lambda: coordinator._settings_failures.get(SERIAL, 0)
            >= _MAX_SETTINGS_READ_FAILURES,
            timeout=15.0,
        )
        attempts = collector.commands.count("PIRI")
        polls = collector.commands.count("GS")
        # Let several more telemetry polls go by; none of them may carry a
        # rating inquiry.
        await _wait_until(
            lambda: collector.commands.count("GS") >= polls + 3, timeout=15.0
        )

        assert collector.commands.count("PIRI") == attempts
        assert coordinator.settings_error(SERIAL)
        controls, _ = await coordinator.async_get_controls_with_values(
            "PN123456789012", 2452, 1, SERIAL
        )
        assert controls == {}
    finally:
        await collector.stop()
        await coordinator.async_shutdown()
