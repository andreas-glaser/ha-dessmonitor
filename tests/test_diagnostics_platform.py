"""Home Assistant reads diagnostics off the integration's diagnostics module."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.dessmonitor import _format_control_fields
from custom_components.dessmonitor import diagnostics as diagnostics_platform
from custom_components.dessmonitor.api import DessMonitorAPI
from custom_components.dessmonitor.const import CONF_LOCAL_LISTEN_IP, DOMAIN
from custom_components.dessmonitor.support_report import short_identity


def test_platform_exposes_the_hooks_home_assistant_looks_up() -> None:
    """Defining these in __init__ alone leaves the download button dead."""
    assert hasattr(diagnostics_platform, "async_get_device_diagnostics")


async def test_device_diagnostics_returns_the_device_payload(
    hass: HomeAssistant,
) -> None:
    """The platform wrapper reaches the real builder and its data."""
    coordinator = MagicMock()
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 6544, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}],
        }
    }
    entry = MagicMock()
    entry.entry_id = "entry-1"
    hass.data[DOMAIN] = {"entry-1": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "SN-1")})

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, entry, device
    )

    # Both downloads are attached to public issues, so neither prints the
    # serial, the collector product number or the user's alias (#53).
    assert report["device_info"]["serial_number"] == short_identity("SN-1")
    assert report["device_info"]["collector_pn"] == short_identity("PN-1")
    assert report["device_info"]["alias"] == short_identity("Inverter")
    assert "SN-1" not in json.dumps(report)
    assert report["device_info"]["device_code"] == 6544
    assert report["raw_data_points"] == 1


async def test_unknown_device_is_reported_not_raised(hass: HomeAssistant) -> None:
    """A stale device entry must not raise inside the diagnostics download."""
    coordinator = MagicMock()
    coordinator.data = {}
    entry = MagicMock()
    entry.entry_id = "entry-1"
    hass.data[DOMAIN] = {"entry-1": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "MISSING")})

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, entry, device
    )

    assert report == {"error": "Device not found"}


def test_an_unread_voltage_control_is_not_invented() -> None:
    """Diagnostics report what was read, never a guess from a 48 V system.

    A voltage control with no reading used to be filled in with a fixed
    estimate such as "58.4 V (Est.)". On the 24 V hardware confirmed for
    devcode 6514 (#56) that number is simply wrong, and a maintainer reading
    the diagnostics file cannot tell an estimate from a measurement.
    """
    from custom_components.dessmonitor import _format_numeric_field

    field = _format_numeric_field(
        "Bulk Charging Voltage",
        {"id": "bse_eybond_read_1"},
        [{"title": "Battery Voltage", "val": "27.4", "unit": "V"}],
    )

    assert field["value"] == "Not read"
    assert field["unit"] == "V"


async def test_the_summary_counts_the_sensors_the_device_publishes(
    hass: HomeAssistant,
) -> None:
    """It counted readings listed under a coordinator key nothing ever set.

    `coordinator.data` is keyed by serial, so `data["sensor_types"]` was always
    absent and every diagnostics download reported 0 sensors created, on a
    device publishing dozens. A reporter attaching that file was handing the
    maintainer a number that described nothing.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 6515, "devaddr": 1, "alias": "Inverter"},
            "data": [
                {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
                {"title": "SOC", "val": "37", "unit": "%"},
                # Resolves only through the devcode's own title mapping.
                {"title": "Total PV Power", "val": "3194", "unit": "W"},
                # A real reading this devcode spells with the vendor's typo.
                {"title": "DC Module Termperature", "val": "42", "unit": "°C"},
                # Identity and timestamp fields, which are not sensors.
                {"title": "Timestamp", "val": "2026-11-02 10:00:39", "unit": ""},
                {"title": "Protocol Number", "val": "3", "unit": ""},
                {"title": "Equipment type", "val": "29440", "unit": ""},
            ],
        }
    }
    entry = MagicMock()
    entry.entry_id = "entry-1"
    hass.data[DOMAIN] = {"entry-1": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "SN-1")})

    summary = (
        await diagnostics_platform.async_get_device_diagnostics(hass, entry, device)
    )["summary"]

    assert summary["total_sensors_created"] == 4
    assert summary["readings_without_a_sensor"] == [
        "Equipment type",
        "Protocol Number",
    ]
    assert summary["last_update"] == "2026-11-02 10:00:39"


async def test_the_summary_does_not_advertise(hass: HomeAssistant) -> None:
    """A file reporters attach to public issues carried marketing copy.

    It claimed "39 Control Fields (vs ~10 in other projects)" on every device,
    whatever that device reported.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 6544, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}],
        }
    }
    entry = MagicMock()
    entry.entry_id = "entry-1"
    hass.data[DOMAIN] = {"entry-1": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "SN-1")})

    summary = (
        await diagnostics_platform.async_get_device_diagnostics(hass, entry, device)
    )["summary"]

    assert "unique_features" not in summary


def test_the_platform_exposes_the_hub_hook_too() -> None:
    """Clicking Download diagnostics on the hub asked for this and got nothing."""
    assert hasattr(diagnostics_platform, "async_get_config_entry_diagnostics")


async def test_hub_diagnostics_cover_every_device_without_identifying_one(
    hass: HomeAssistant,
) -> None:
    """The acceptance criterion from #60, asserted on the real output."""
    serial = "SN-SECRET-0001"
    collector_pn = "Q0000SECRETPN0"
    coordinator = MagicMock()
    coordinator.is_hybrid = False
    coordinator.last_update_success = True
    coordinator.cloud_revision = 7
    coordinator.stale_cloud_serials = frozenset({serial})
    coordinator.update_interval = timedelta(seconds=300)
    coordinator.data = {
        serial: {
            "collector": {"pn": collector_pn, "alias": "Shed roof"},
            "device": {"devcode": 6515, "devaddr": 1, "alias": "Solar"},
            "data": [
                {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
                {"title": "Daily Generation", "val": "10.2", "unit": "kWh"},
                {"title": "Data Source", "val": "Cached Cloud", "unit": ""},
                {"title": "Timestamp", "val": "2026-11-02 10:00:39", "unit": ""},
            ],
        }
    }
    coordinator.api.get_device_control_fields = AsyncMock(return_value={})
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {
        "username": "someone@example.com",
        "password": "hunter2",
        "company_key": "bnrl_frRFjEz8Mkn",
        "api_profile": "dessmonitor_ess",
        "local_expected_product_number": collector_pn,
    }
    entry.options = {"local_mode": "disabled", "update_interval": 300}
    hass.data[DOMAIN] = {"entry-1": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    serialized = json.dumps(report)
    for secret in (serial, collector_pn, "hunter2", "someone@example.com"):
        assert secret not in serialized
    assert report["entry_data"]["password"] == "**redacted**"
    assert report["entry_data"]["username"] == "**redacted**"
    assert report["entry_data"]["company_key"] == "**redacted**"
    assert report["entry_data"]["local_expected_product_number"].startswith("sha256:")

    assert report["integration"]["version"]
    assert report["coordinator"]["cloud_revision"] == 7
    assert report["coordinator"]["devices_on_a_retained_cloud_payload"] == 1

    (device,) = report["devices"]
    assert device["devcode"] == 6515
    assert device["device_identity"].startswith("sha256:")
    assert device["support"]["status"] == "partial"
    assert device["support"]["unresolved_with_unit"] == [
        {"title": "Daily Generation", "unit": "kWh", "sample": "10.2"}
    ]
    assert device["data_source"] == "Cached Cloud"


async def test_hub_diagnostics_survive_an_unloaded_entry(hass: HomeAssistant) -> None:
    """A download must not raise while the entry is reloading."""
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"username": "someone@example.com", "password": "hunter2"}
    entry.options = {}
    hass.data[DOMAIN] = {}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    assert report["error"] == "The config entry is not loaded"
    assert "hunter2" not in json.dumps(report)


async def test_a_device_whose_controls_fail_still_appears(hass: HomeAssistant) -> None:
    """The reporter with a timing-out account is the one who needs this file."""
    coordinator = MagicMock()
    coordinator.is_hybrid = False
    coordinator.last_update_success = True
    coordinator.cloud_revision = 1
    coordinator.stale_cloud_serials = frozenset()
    coordinator.update_interval = timedelta(seconds=300)
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 6515, "devaddr": 1, "alias": "Solar"},
            "data": [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}],
        }
    }
    coordinator.api.get_device_control_fields = AsyncMock(
        side_effect=RuntimeError("ERR_TIMEOUT")
    )
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"username": "u", "password": "p"}
    entry.options = {}
    hass.data[DOMAIN] = {"entry-1": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    (device,) = report["devices"]
    assert device["support"]["status"] == "supported"
    assert "ERR_TIMEOUT" in device["control_error"]


async def test_the_hub_report_is_json_serializable(hass: HomeAssistant) -> None:
    """Home Assistant writes this file as JSON; a set in it would be a 500."""
    coordinator = MagicMock()
    coordinator.is_hybrid = True
    coordinator.last_update_success = True
    coordinator.cloud_revision = 2
    coordinator.stale_cloud_serials = frozenset({"SN-1"})
    coordinator.update_interval = timedelta(seconds=300)
    coordinator.local_setup_errors = ["one route could not start"]
    local = MagicMock()
    local.connected = True
    local.last_update_success = True
    # Local control is off on this entry, which is the default, so the local
    # side offers no settings; a mock that answers for every attribute would
    # otherwise put objects in the file that cannot be written as JSON.
    local.control_enabled = False
    local.settings_snapshot.return_value = None
    local.settings_error.return_value = None
    local.diagnostics.return_value = {
        "poll_interval_seconds": 60,
        "driver": "p17",
        "session": {"connected": True, "answers_late": False},
        "devices": {},
    }
    local.device_code = 2452
    local.data = {"SN-1": {}}
    coordinator.locals = (local,)
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Solar"},
            "data": [{"title": "Grid frequency", "val": "50.1", "unit": "Hz"}],
        }
    }
    coordinator.api.get_device_control_fields = AsyncMock(return_value={})
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"username": "u", "password": "p"}
    entry.options = {}
    hass.data[DOMAIN] = {"entry-1": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    assert json.loads(json.dumps(report))["local"]["transports"][0]["device_code"] == (
        2452
    )


async def test_a_local_transport_reports_the_devices_it_saw(
    hass: HomeAssistant,
) -> None:
    """A local device that matches no cloud device stays invisible otherwise.

    The overlay matches by serial, or by collector and RS485 address together.
    When it matches nothing the device keeps cloud telemetry and says so only
    as "Cloud" on the Data Source sensor, and the file recorded nothing about
    what the local side had seen, so the mismatch could not be diagnosed from
    it (#61).
    """
    coordinator = MagicMock()
    coordinator.is_hybrid = True
    coordinator.last_update_success = True
    coordinator.cloud_revision = 2
    coordinator.stale_cloud_serials = frozenset()
    coordinator.update_interval = timedelta(seconds=300)
    coordinator.local_setup_errors = []
    local = MagicMock()
    local.connected = True
    local.last_update_success = True
    # Local control is off on this entry, which is the default, so the local
    # side offers no settings; a mock that answers for every attribute would
    # otherwise put objects in the file that cannot be written as JSON.
    local.control_enabled = False
    local.settings_snapshot.return_value = None
    local.settings_error.return_value = None
    local.diagnostics.return_value = {
        "poll_interval_seconds": 60,
        "driver": "p17",
        "session": {"connected": True, "answers_late": False},
        "devices": {},
    }
    local.device_code = 258
    local.data = {
        "LOCAL-SN": {
            "collector": {"pn": "PN-1"},
            "device": {
                "devaddr": 1,
                "local_address_verified": False,
                "local_protocol": "pi30",
            },
            "data": [{"title": "Battery Voltage", "val": "26.6", "unit": "V"}],
        }
    }
    coordinator.locals = (local,)
    # The cloud lists the same collector's inverter at another address.
    coordinator.data = {
        "CLOUD-SN": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 2477, "devaddr": 5, "alias": "Solar"},
            "data": [{"title": "Battery Voltage", "val": "26.6", "unit": "V"}],
        }
    }
    coordinator.api.get_device_control_fields = AsyncMock(return_value={})
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"username": "u", "password": "p"}
    entry.options = {}
    hass.data[DOMAIN] = {"entry-1": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    (seen,) = json.loads(json.dumps(report))["local"]["transports"][0]["devices_seen"]
    assert seen["device_address"] == 1
    assert seen["address_verified"] is False
    assert seen["protocol"] == "pi30"
    assert seen["readings"] == 1
    # Comparable to the cloud device's own entry, and naming neither.
    assert seen["device_identity"] == short_identity("LOCAL-SN")
    assert seen["collector_identity"] == short_identity("PN-1")
    assert "LOCAL-SN" not in json.dumps(report)
    assert "PN-1" not in json.dumps(report)


async def test_control_fields_format_the_shape_the_api_returns(
    cloud_transport,
) -> None:
    """Device diagnostics returned 500 on any device with an option control.

    `get_device_control_fields` returns each field's options as a dict of
    option key to label, and the diagnostics formatter read them as a list of
    dicts. Iterating a dict yields its string keys, so `opt["key"]` raised
    `TypeError: string indices must be integers`, and the whole download
    failed. Every other test here stubs the control fields out, so the
    producer and the consumer had never run against each other.
    """
    session, connector = cloud_transport
    connector.payload = {
        "err": 0,
        "dat": {
            "field": [
                {
                    "id": "los_output_source_priority",
                    "name": "Output priority",
                    "item": [
                        {"key": "0", "val": "Utility first"},
                        {"key": "2", "val": "SBU priority"},
                    ],
                },
                {
                    "id": "bse_eybond_read_1",
                    "name": "Bulk Charging Voltage",
                    "unit": "V",
                },
            ]
        },
    }
    api = DessMonitorAPI("test-user", "test-password", session=session)
    api.token, api.secret = "test-token", "test-secret"

    fields = await api.get_device_control_fields("PN-1", 2376, 1, "SN-1")
    formatted = _format_control_fields(
        fields, [{"title": "Output priority", "val": "SBU", "unit": ""}]
    )

    assert formatted["Output priority"]["options"] == [
        "0: Utility first",
        "2: SBU priority",
    ]
    assert formatted["Output priority"]["id"] == "los_output_source_priority"
    # PRIORITY_MAPPINGS turns the reading "SBU" into option key 2, which has
    # to resolve through the same mapping rather than fall back to the key.
    assert formatted["Output priority"]["value"] == "SBU priority"
    assert formatted["Bulk Charging Voltage"]["unit"] == "V"


async def test_diagnostics_report_the_control_values_the_entities_show(
    hass: HomeAssistant,
) -> None:
    """The file said "Not Set" for controls Home Assistant was displaying.

    Most control fields never appear in the telemetry payload, and the
    formatters looked nowhere else, so a device download reported 36 of 40
    controls as having no value while 131 of 140 control entities on that
    account held one (#60). An explicit read lands in the coordinator's value
    cache, which is the same place the entities read from.
    """
    coordinator = MagicMock()
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 2376, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}],
        }
    }
    coordinator.ctrl_value_cache = {
        "SN-1": {"sys_eybond_ctrl_51": "3", "bse_eybond_read_1": "56.4"}
    }
    coordinator.api.get_device_control_fields = AsyncMock(
        return_value={
            "Buzzer Mode": {
                "id": "sys_eybond_ctrl_51",
                "type": "options",
                "options": {"0": "Beeps OFF", "3": "Beeps only in fault mode"},
            },
            "Bulk Charging Voltage": {
                "id": "bse_eybond_read_1",
                "type": "value",
                "unit": "V",
            },
            "Backlight Control": {
                "id": "sys_eybond_ctrl_53",
                "type": "options",
                "options": {"0": "Backlight Timing Off", "1": "Backlight On"},
            },
        }
    )
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    entry = MagicMock()
    entry.entry_id = "entry-1"
    hass.data[DOMAIN] = {"entry-1": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "SN-1")})

    config = (await diagnostics_platform.async_get_device_diagnostics(hass, entry, device))[
        "configuration"
    ]

    # Read through an explicit control read, and reported as its label.
    assert config["Buzzer Mode"]["value"] == "Beeps only in fault mode"
    assert config["Bulk Charging Voltage"]["value"] == "56.4"
    # Never read, and said so rather than claiming the control is unset.
    assert config["Backlight Control"]["value"] == "Not read"


async def test_hub_diagnostics_do_not_disclose_local_network_addresses(
    hass: HomeAssistant,
) -> None:
    """The LAN addresses local mode is configured with are identifiers (#53).

    A reporter attached this file to a public issue with their collector and
    Home Assistant addresses in it. What support needs from those two fields is
    the family, the scope and whether they share a subnet, so that is what the
    download now carries.
    """
    coordinator = MagicMock()
    coordinator.is_hybrid = False
    coordinator.last_update_success = True
    coordinator.cloud_revision = 1
    coordinator.stale_cloud_serials = frozenset()
    coordinator.update_interval = timedelta(seconds=300)
    coordinator.data = {}
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"username": "someone@example.com", "password": "hunter2"}
    entry.options = {
        "local_mode": "prefer_local",
        "local_listen_ip": "192.168.18.134",
        "local_collector_ips": ["192.168.18.27", "10.11.12.13"],
        "local_poll_interval": 10,
    }
    hass.data[DOMAIN] = {"entry-1": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    serialized = json.dumps(report)
    for address in ("192.168.18.134", "192.168.18.27", "10.11.12.13"):
        assert address not in serialized

    options = report["entry_options"]
    # The listen address shares the first collector's subnet and not the
    # second's, which is the fact a local-mode thread actually turns on.
    assert options["local_listen_ip"] == "private ipv4 in subnet 1"
    assert options["local_collector_ips"] == [
        "private ipv4 in subnet 1",
        "private ipv4 in subnet 2",
    ]
    assert options["local_poll_interval"] == 10


async def test_a_local_setup_error_does_not_print_an_address(
    hass: HomeAssistant,
) -> None:
    """The one field in the download that was passed through verbatim.

    Binding the listen socket fails with the address in the message - "error
    while attempting to bind on address (\'192.168.0.72\', 8899)" in the #66
    download - so a reporter's LAN address reached a public attachment while
    the same address was described rather than printed in the options block.
    The port and the errno are the diagnostic value and stay.
    """
    coordinator = MagicMock()
    coordinator.is_hybrid = True
    coordinator.last_update_success = True
    coordinator.cloud_revision = 1
    coordinator.stale_cloud_serials = frozenset()
    coordinator.update_interval = timedelta(seconds=300)
    coordinator.local_setup_errors = [
        "[Errno 98] error while attempting to bind on address "
        "('192.168.0.72', 8899): [errno 98] address in use"
    ]
    coordinator.locals = ()
    coordinator.data = {}
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {}
    entry.options = {CONF_LOCAL_LISTEN_IP: "192.168.0.72"}
    hass.data[DOMAIN] = {"entry-1": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    (error,) = report["local"]["setup_errors"]
    assert "192.168.0.72" not in json.dumps(report)
    assert "private ipv4 in subnet 1" in error
    # The subnet numbering is shared with the options, so a reader can still
    # see that the failing bind and the configured listen address are one.
    assert report["entry_options"][CONF_LOCAL_LISTEN_IP] == (
        "private ipv4 in subnet 1"
    )
    assert "8899" in error and "Errno 98" in error


def test_a_message_without_an_address_is_left_alone() -> None:
    """A timestamp is not an address, and the IPv6 pattern matches one."""
    from custom_components.dessmonitor import _redacted_message

    text = "two routes could not start, first occurred: 10:32:34"

    assert _redacted_message(text, {}) == text


def test_every_config_key_is_classified() -> None:
    """A new option must not reach a public issue by being forgotten (#53).

    The download used to publish any key nobody had classified, which is how a
    reporter's collector and listen addresses ended up in an attachment. Adding
    a `CONF_*` constant now fails here until its disclosure is decided.
    """
    from custom_components.dessmonitor import _ENTRY_DISCLOSURE
    from custom_components.dessmonitor import const

    config_keys = {
        getattr(const, name)
        for name in dir(const)
        if name.startswith("CONF_") and isinstance(getattr(const, name), str)
    }

    unclassified = sorted(config_keys - set(_ENTRY_DISCLOSURE))
    assert not unclassified, (
        f"these configuration keys have no disclosure decision: {unclassified}. "
        "Add each to _ENTRY_DISCLOSURE as publish, redact, hash or "
        "describe_address."
    )


async def test_no_configured_value_reaches_the_download_verbatim(
    hass: HomeAssistant,
) -> None:
    """The support guide promises no credentials and no identifiers.

    It promised that while the file carried two LAN addresses, because the
    tests asserted four specific secrets rather than the categorical claim.
    This sets every known configuration key to a recognisable value and
    asserts that none of them appears in the file as written.
    """
    from custom_components.dessmonitor import _ENTRY_DISCLOSURE, _PUBLISH
    from custom_components.dessmonitor import const

    sentinels: dict[str, str] = {}
    for name in dir(const):
        if not name.startswith("CONF_"):
            continue
        key = getattr(const, name)
        if not isinstance(key, str) or _ENTRY_DISCLOSURE.get(key) is _PUBLISH:
            continue
        sentinels[key] = f"sentinel-{name.lower()}-9f3b"

    assert sentinels, "no redacted configuration keys to check"

    coordinator = MagicMock()
    coordinator.is_hybrid = False
    coordinator.last_update_success = True
    coordinator.cloud_revision = 1
    coordinator.stale_cloud_serials = frozenset()
    coordinator.update_interval = timedelta(seconds=300)
    coordinator.data = {}
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = dict(sentinels)
    entry.options = dict(sentinels)
    hass.data[DOMAIN] = {"entry-1": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    serialized = json.dumps(report)
    leaked = sorted(key for key, value in sentinels.items() if value in serialized)
    assert not leaked, f"these configured values reached the download: {leaked}"
    # Each key is still present, so a reader can tell a configured value from
    # an absent one.
    for key in sentinels:
        assert key in report["entry_data"]


async def test_the_device_download_carries_the_same_support_report(
    hass: HomeAssistant,
) -> None:
    """Either button produces usable devcode evidence.

    The device download named the readings that reached no entity and nothing
    else: no value, no unit, no control-field correlation and no checksum. Four
    of the five files on the devcode issues open when this was written were
    device downloads, so four reporters were asked for a second file before
    their first could be used, and the triage tool refused all four as "not a
    devcode analysis or diagnostics download".
    """
    coordinator = MagicMock()
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 2477, "devaddr": 5, "alias": "Inverter"},
            "data": [
                {"title": "Battery Voltage", "val": "24.3", "unit": "V"},
                {"title": "Nominal AC Voltage", "val": "230.0", "unit": "V"},
                {"title": "Bulk Charging Voltage", "val": "28.8", "unit": "V"},
            ],
        }
    }
    coordinator.api.get_device_control_fields = AsyncMock(return_value={})
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    coordinator.ctrl_value_cache = {}
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {}
    hass.data[DOMAIN] = {"entry-1": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "SN-1")})

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, entry, device
    )
    support = report["support_report"]

    assert support["devcode"] == 2477
    assert support["source"] == "device_diagnostics"
    # Every reading with its unit and its resolved key, which is what a
    # maintainer works from and what the coverage guard reads.
    assert {row["title"]: row["unit"] for row in support["readings"]} == {
        "Battery Voltage": "V",
        "Nominal AC Voltage": "V",
        "Bulk Charging Voltage": "V",
    }
    assert support["support"]["unresolved_with_unit"] == []
    # And no identifier, as the entry download promises.
    assert support["device_identity"] == short_identity("SN-1")
    assert "SN-1" not in json.dumps(report)


async def test_a_device_download_is_read_as_evidence(hass: HomeAssistant) -> None:
    """``normalized_reports`` reads the device shape, so the tooling does."""
    from custom_components.dessmonitor.support_report import normalized_reports

    coordinator = MagicMock()
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 2341, "devaddr": 5, "alias": "Inverter"},
            "data": [{"title": "Battery Capacity", "val": "57", "unit": "%"}],
        }
    }
    coordinator.api.get_device_control_fields = AsyncMock(return_value={})
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    coordinator.ctrl_value_cache = {}
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {}
    hass.data[DOMAIN] = {"entry-1": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "SN-1")})

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, entry, device
    )

    # As the reporter attaches it: Home Assistant wraps the hook's return
    # value under "data" beside its own host sections.
    records = normalized_reports({"data": report})

    assert [record["devcode"] for record in records] == [2341]
    assert records[0]["units"] == {"Battery Capacity": "%"}
    assert records[0]["checksum_valid"] is True


def _local_only_coordinator(hass: HomeAssistant, entry_data: dict[str, object]):
    """Build the real local coordinator, without binding any socket."""
    from custom_components.dessmonitor.local.coordinator import (
        DessMonitorLocalCoordinator,
    )

    coordinator = DessMonitorLocalCoordinator(hass, entry_data)
    coordinator.async_set_updated_data(
        {
            "SN-LOCAL-1": {
                "collector": {"pn": "Q0000PN0001", "ip": "192.168.18.27"},
                "device": {
                    "devcode": 258,
                    "devaddr": 1,
                    "local_protocol": "pi30",
                    "local_address_verified": True,
                    "connection_type": "local",
                },
                "data": [
                    {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
                    {"title": "Data Source", "val": "Local", "unit": ""},
                    {"title": "Timestamp", "val": "2026-11-17 18:29:05", "unit": ""},
                ],
            }
        }
    )
    return coordinator


@pytest.mark.usefixtures("socket_enabled")
async def test_a_local_only_entry_can_be_downloaded(hass: HomeAssistant) -> None:
    """The hub download raised AttributeError on every local-only entry (#86).

    Asserted against the real local coordinator rather than a mock of one:
    a mock answers for any attribute, which is why the entry download could
    reach a stable release while failing on the mode whose owners are asked
    for a download most often.
    """
    entry_data: dict[str, object] = {
        "connection_type": "local",
        CONF_LOCAL_LISTEN_IP: "192.168.18.134",
        "local_collector_ip": "192.168.18.27",
        "local_tcp_port": 0,
        "local_udp_port": 58899,
        "local_poll_interval": 60,
        "local_device_address": 1,
    }
    coordinator = _local_only_coordinator(hass, entry_data)
    entry = MagicMock()
    entry.entry_id = "entry-local"
    entry.data = dict(entry_data)
    entry.options = {}
    hass.data[DOMAIN] = {"entry-local": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    serialized = json.dumps(report)
    assert "192.168.18.134" not in serialized
    assert "192.168.18.27" not in serialized
    assert report["coordinator"]["local_only"] is True
    assert report["coordinator"]["hybrid"] is False
    # Retention is a cloud mechanism and a local entry has no cloud payload,
    # so the counter that depends on one is absent rather than invented.
    assert "devices_on_a_retained_cloud_payload" not in report["coordinator"]
    (transport,) = report["local"]["transports"]
    assert transport["devices"] == 1
    (seen,) = transport["devices_seen"]
    assert seen["protocol"] == "pi30"
    assert seen["device_identity"].startswith("sha256:")
    (device,) = report["devices"]
    assert device["devcode"] == 258
    # No cloud client exists here, so the file says nothing was asked for
    # rather than reporting a failed API call.
    assert "control_error" not in device


@pytest.mark.usefixtures("socket_enabled")
async def test_a_local_device_can_be_downloaded(hass: HomeAssistant) -> None:
    """The device button has to work on a local entry too (#86)."""
    coordinator = _local_only_coordinator(
        hass,
        {
            "connection_type": "local",
            CONF_LOCAL_LISTEN_IP: "192.168.18.134",
            "local_collector_ip": "192.168.18.27",
            "local_tcp_port": 0,
        },
    )
    entry = MagicMock()
    entry.entry_id = "entry-local"
    entry.data = {}
    entry.options = {}
    hass.data[DOMAIN] = {"entry-local": coordinator}
    device = DeviceEntry(identifiers={(DOMAIN, "SN-LOCAL-1")})

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, entry, device
    )

    assert report["support_report"]["devcode"] == 258
    assert "battery_config_error" not in report
    assert report["local_control"] == {"enabled": False}


def test_a_local_tunnel_code_is_not_a_missing_devcode_profile(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The log told owners to request support for a collector tunnel code (#86)."""
    from custom_components.dessmonitor.device_support.device_registry import (
        _WARNED_UNSUPPORTED_DEVCODES,
        apply_devcode_transformations,
        note_local_transport_devcode,
    )

    _WARNED_UNSUPPORTED_DEVCODES.discard(258)
    note_local_transport_devcode(258)
    with caplog.at_level("WARNING"):
        point = apply_devcode_transformations(258, {"title": "Battery Voltage"})

    assert point["title"] == "Battery Voltage"
    assert "Unsupported devcode" not in caplog.text


@pytest.mark.usefixtures("socket_enabled")
async def test_a_local_entry_download_carries_the_probe_evidence(
    hass: HomeAssistant,
) -> None:
    """The highest-value gap in #63, asserted on the real objects.

    ``ProbeDiagnostics.as_dict()`` reached the debug log and nothing else, and
    so did the queries a driver had stopped sending, the collector session and
    the poll age. That is the difference between a local-mode thread costing
    one attached file and costing two weeks of logs.
    """
    from custom_components.dessmonitor.local.diagnostics import (
        ProbeAttempt,
        ProbeDiagnostics,
    )
    from custom_components.dessmonitor.local.drivers import LocalDevice

    entry_data: dict[str, object] = {
        "connection_type": "local",
        CONF_LOCAL_LISTEN_IP: "192.168.18.134",
        "local_collector_ip": "192.168.18.27",
        "local_tcp_port": 0,
        "local_poll_interval": 30,
    }
    coordinator = _local_only_coordinator(hass, entry_data)
    probe = ProbeDiagnostics()
    probe.record(
        ProbeAttempt(
            protocol="pi30",
            command="QPIRI",
            device_code=258,
            collector_address=1,
            device_address=1,
            response_bytes=98,
            elapsed_ms=240,
        )
    )
    probe.record(
        ProbeAttempt(
            protocol="pi30",
            command="QPIGS",
            device_code=258,
            collector_address=1,
            device_address=1,
            outcome="timeout",
        )
    )
    coordinator._probe = probe
    coordinator._devices = {
        "SN-LOCAL-1": LocalDevice(
            driver_key="pi30",
            transport_device_code=258,
            collector_address=1,
            device_address=1,
            entity_device_code=258,
            serial="SN-LOCAL-1",
            model="PI30 inverter",
            firmware="00073.08",
            disabled_queries={"QPIGS2"},
            optional_query_failures={"QPIGS2": 3},
        )
    }
    coordinator._polled_serials = {"SN-LOCAL-1"}
    entry = MagicMock()
    entry.entry_id = "entry-local"
    entry.data = dict(entry_data)
    entry.options = {}
    hass.data[DOMAIN] = {"entry-local": coordinator}

    report = await diagnostics_platform.async_get_config_entry_diagnostics(hass, entry)

    (transport,) = report["local"]["transports"]
    assert transport["poll_interval_seconds"] == 30
    assert transport["discovery"]["outcomes"] == {"success": 1, "timeout": 1}
    assert [attempt["command"] for attempt in transport["discovery"]["attempts"]] == [
        "QPIRI",
        "QPIGS",
    ]
    assert transport["session"]["request_timeout_seconds"] == 3.0
    assert transport["seconds_since_a_successful_poll"] is None
    (seen,) = transport["devices_seen"]
    assert seen["disabled_queries"] == ["QPIGS2"]
    assert seen["optional_query_failures"] == {"QPIGS2": 3}

    # Payload-free and identifier-free, like the rest of the file: command
    # names and numbers only, no serial, no collector product number, no
    # network address.
    serialized = json.dumps(report)
    for secret in ("SN-LOCAL-1", "Q0000PN0001", "192.168.18.27", "192.168.18.134"):
        assert secret not in serialized


def test_a_reading_row_carries_the_unit_its_entity_publishes() -> None:
    """Item 5 of #63: the raw unit alone could not show a scale mismatch.

    The PI18 watt-hour total sitting on a kWh sensor had to be inferred by
    comparing it against the cloud's own parameters; with both units on the
    row it is legible at a glance.
    """
    from custom_components.dessmonitor.support_report import build_support_report

    report = build_support_report(
        devcode=6515,
        readings=[
            {"title": "Energy Total", "val": "10104399", "unit": "Wh"},
            {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
            {"title": "Timestamp", "val": "2026-11-16 18:26:52", "unit": ""},
        ],
    )

    rows = {row["title"]: row for row in report["readings"]}
    assert rows["Energy Total"]["sensor_unit"] == "kWh"
    assert rows["Battery Voltage"]["sensor_unit"] == "V"
    # A row that reaches no sensor has no sensor unit to report.
    assert rows["Timestamp"]["sensor_unit"] is None
