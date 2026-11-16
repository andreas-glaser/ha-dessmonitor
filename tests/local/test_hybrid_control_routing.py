"""Which transport a hybrid write takes, and why.

A cloud control and a local setting are the same register under two names, and
nothing in either payload says they are the same one. These hold the rule that
decides it: a devcode profile declaration, or names that normalise to the same
string. Anything else keeps the cloud path every installation has always used,
and any local failure falls back to it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dessmonitor.const import (
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_CONTROL,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    LOCAL_CONTROL_ENABLED,
)
from custom_components.dessmonitor.control_values import (
    TRANSPORT_CLOUD,
    TRANSPORT_LOCAL,
    ControlWriteResult,
)
from custom_components.dessmonitor.local.hybrid import DessMonitorHybridCoordinator
from custom_components.dessmonitor.local.settings import SettingNotWritable

CLOUD_SERIAL = "CLOUD-SERIAL"
LOCAL_SERIAL = "LOCAL-SERIAL"


def _hybrid(hass: HomeAssistant, *, control: bool = True) -> DessMonitorHybridCoordinator:
    """Create a hybrid coordinator without opening sockets."""
    api = MagicMock(token="token", secret="secret", close=AsyncMock())
    api.set_device_control_value = AsyncMock(return_value={"err": 0})
    local_config = {
        CONF_LOCAL_LISTEN_IP: "127.0.0.1",
        CONF_LOCAL_COLLECTOR_IP: "127.0.0.2",
        CONF_LOCAL_TCP_PORT: 0,
        CONF_LOCAL_UDP_PORT: 9,
    }
    if control:
        local_config[CONF_LOCAL_CONTROL] = LOCAL_CONTROL_ENABLED
    coordinator = DessMonitorHybridCoordinator(hass, api, 300, local_config, "hybrid")
    coordinator.data = {
        CLOUD_SERIAL: {
            "collector": {"pn": "COLLECTOR-1"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Main"},
            "data": [],
        }
    }
    coordinator.ctrl_field_cache = {
        CLOUD_SERIAL: {
            "Battery Bulk Voltage": {"id": "bse_bulk", "type": "value"},
            "Bulk Charging Voltage": {"id": "vendor_bulk", "type": "value"},
        }
    }
    return coordinator


def _local_snapshot(values: dict[str, str] | None = None):
    """Build a settings snapshot for the PI18 table, as the backend would."""
    from custom_components.dessmonitor.local.p17_settings import settings_for

    ratings = (
        "2300,217,2300,500,217,5000,5000,480,500,540,450,560,540,2,010,060,1,1,1,"
        "9,1,0,0,0,1,00"
    ).split(",")
    from custom_components.dessmonitor.local.writer import SettingsSnapshot

    settings = settings_for(tuple(ratings))
    enumerations = {"MCHGCR": ("010", "060"), "MUCHGCR": ("002", "010")}
    reported = {
        setting.key: decoded
        for setting in settings
        if (decoded := setting.decode(ratings[setting.index], enumerations)) is not None
    }
    reported.update(values or {})
    return SettingsSnapshot(settings, reported, enumerations, ())


def _wire_local(coordinator, *, snapshot=None, writes=None) -> MagicMock:
    """Give the hybrid entry one local transport that has discovered a device."""
    local = coordinator.locals[0]
    local.async_set_updated_data(
        {
            LOCAL_SERIAL: {
                "collector": {"pn": "COLLECTOR-1"},
                "device": {"devcode": 2452, "devaddr": 1},
                "data": [],
            }
        }
    )
    local._settings[LOCAL_SERIAL] = snapshot if snapshot is not None else _local_snapshot()
    local.async_set_control_value = writes or AsyncMock(
        return_value=ControlWriteResult(
            value="57.0", transport=TRANSPORT_LOCAL, verified=True
        )
    )
    return local


async def test_a_control_named_like_a_local_setting_writes_locally(
    hass: HomeAssistant,
) -> None:
    """Identical names, normalised, are evidence enough to pair the two."""
    coordinator = _hybrid(hass)
    local = _wire_local(coordinator)
    try:
        result = await coordinator.async_set_control_value(
            CLOUD_SERIAL, "bse_bulk", "57.0", control_name="Battery Bulk Voltage"
        )

        assert result.transport == TRANSPORT_LOCAL
        assert result.verified is True
        local.async_set_control_value.assert_awaited_once()
        assert local.async_set_control_value.await_args.args[:3] == (
            LOCAL_SERIAL,
            "battery_bulk_voltage",
            "57.0",
        )
        coordinator.api.set_device_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_a_control_nothing_pairs_with_takes_the_cloud(
    hass: HomeAssistant,
) -> None:
    """The vendor's own spelling is not a pairing, so the cloud carries it.

    "Bulk Charging Voltage" is the same register as the local setting, and the
    only thing that says so is a download. Until a devcode profile declares
    it, this write goes where it always went.
    """
    coordinator = _hybrid(hass)
    local = _wire_local(coordinator)
    try:
        result = await coordinator.async_set_control_value(
            CLOUD_SERIAL, "vendor_bulk", "57.0", control_name="Bulk Charging Voltage"
        )

        assert result.transport == TRANSPORT_CLOUD
        assert result.verified is False
        local.async_set_control_value.assert_not_awaited()
        coordinator.api.set_device_control_value.assert_awaited_once_with(
            pn="COLLECTOR-1",
            devcode=2452,
            devaddr=1,
            sn=CLOUD_SERIAL,
            param_id="vendor_bulk",
            value="57.0",
        )
    finally:
        await coordinator.async_shutdown()


async def test_a_declared_pairing_routes_a_differently_named_control(
    hass: HomeAssistant,
) -> None:
    """A profile declaration is what connects two unlike names."""
    coordinator = _hybrid(hass)
    local = _wire_local(coordinator)
    try:
        with patch(
            "custom_components.dessmonitor.local.hybrid.local_control_setting",
            return_value="battery_bulk_voltage",
        ) as declared:
            result = await coordinator.async_set_control_value(
                CLOUD_SERIAL,
                "vendor_bulk",
                "57.0",
                control_name="Bulk Charging Voltage",
            )

        declared.assert_called_once_with(2452, "vendor_bulk")
        assert result.transport == TRANSPORT_LOCAL
        assert local.async_set_control_value.await_args.args[1] == "battery_bulk_voltage"
    finally:
        await coordinator.async_shutdown()


async def test_a_declaration_the_inverter_does_not_report_is_not_used(
    hass: HomeAssistant,
) -> None:
    """A pairing is only usable where the setting has a value to verify against."""
    coordinator = _hybrid(hass)
    local = _wire_local(coordinator)
    try:
        with patch(
            "custom_components.dessmonitor.local.hybrid.local_control_setting",
            return_value="not_reported_here",
        ):
            result = await coordinator.async_set_control_value(
                CLOUD_SERIAL, "vendor_bulk", "57.0"
            )

        assert result.transport == TRANSPORT_CLOUD
        local.async_set_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "failure",
    [
        SettingNotWritable("the inverter refused it"),
        TimeoutError("the inverter did not answer"),
        ConnectionError("the collector disconnected"),
    ],
)
async def test_a_local_failure_falls_back_to_the_cloud(
    hass: HomeAssistant, failure: Exception
) -> None:
    """The owner asked for a setting to change, not for a transport.

    An unverified or refused local write still leaves the cloud path, which is
    what this installation used before local control existed, so the attempt
    is not abandoned on the strength of one transport.
    """
    coordinator = _hybrid(hass)
    local = _wire_local(coordinator, writes=AsyncMock(side_effect=failure))
    try:
        result = await coordinator.async_set_control_value(
            CLOUD_SERIAL, "bse_bulk", "57.0", control_name="Battery Bulk Voltage"
        )

        assert result.transport == TRANSPORT_CLOUD
        local.async_set_control_value.assert_awaited_once()
        coordinator.api.set_device_control_value.assert_awaited_once()
    finally:
        await coordinator.async_shutdown()


async def test_local_control_turned_off_leaves_hybrid_exactly_as_it_was(
    hass: HomeAssistant,
) -> None:
    """The option is the switch, and it defaults to off.

    A hybrid installation that upgrades gets no change in behaviour at all:
    the same cloud call, with the same arguments, for every control.
    """
    coordinator = _hybrid(hass, control=False)
    local = _wire_local(coordinator)
    try:
        result = await coordinator.async_set_control_value(
            CLOUD_SERIAL, "bse_bulk", "57.0", control_name="Battery Bulk Voltage"
        )

        assert result.transport == TRANSPORT_CLOUD
        local.async_set_control_value.assert_not_awaited()
        coordinator.api.set_device_control_value.assert_awaited_once()
    finally:
        await coordinator.async_shutdown()


async def test_an_unpaired_local_device_is_never_written_to(
    hass: HomeAssistant,
) -> None:
    """A write goes to the inverter whose readings are being published.

    The pairing reuses the telemetry overlay's own matching, so a local device
    that the overlay refuses to pair - a second inverter behind the collector
    at an address the cloud does not confirm - cannot receive another device's
    setting.
    """
    coordinator = _hybrid(hass)
    local = _wire_local(coordinator)
    local.data[LOCAL_SERIAL]["device"]["devaddr"] = 7
    local.data[LOCAL_SERIAL]["device"]["local_address_verified"] = True
    coordinator.data[CLOUD_SERIAL]["device"]["devaddr"] = 1
    coordinator.data["CLOUD-SERIAL-2"] = {
        "collector": {"pn": "COLLECTOR-1"},
        "device": {"devcode": 2452, "devaddr": 2, "alias": "Second"},
        "data": [],
    }
    try:
        result = await coordinator.async_set_control_value(
            CLOUD_SERIAL, "bse_bulk", "57.0", control_name="Battery Bulk Voltage"
        )

        assert result.transport == TRANSPORT_CLOUD
        local.async_set_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_a_device_with_no_local_settings_yet_takes_the_cloud(
    hass: HomeAssistant,
) -> None:
    """Before the first settings read-back there is nothing to pair against."""
    coordinator = _hybrid(hass)
    local = _wire_local(coordinator)
    local._settings.clear()
    try:
        result = await coordinator.async_set_control_value(
            CLOUD_SERIAL, "bse_bulk", "57.0", control_name="Battery Bulk Voltage"
        )

        assert result.transport == TRANSPORT_CLOUD
        local.async_set_control_value.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_the_profile_renamed_control_is_paired_too(hass: HomeAssistant) -> None:
    """Both the platform's field name and the profile's rename are compared.

    A vendor spells the field either way, and a devcode profile renames it to
    this project's own vocabulary, which is the vocabulary the local settings
    use.
    """
    coordinator = _hybrid(hass)
    coordinator.ctrl_field_cache[CLOUD_SERIAL] = {
        "bat_bulk_v": {"id": "bse_bulk", "type": "value"}
    }
    local = _wire_local(coordinator)
    try:
        with patch(
            "custom_components.dessmonitor.local.hybrid.map_control_field",
            return_value="Battery Bulk Voltage",
        ):
            result = await coordinator.async_set_control_value(
                CLOUD_SERIAL, "bse_bulk", "57.0"
            )

        assert result.transport == TRANSPORT_LOCAL
    finally:
        await coordinator.async_shutdown()
