"""Home Assistant reads diagnostics off the integration's diagnostics module."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.dessmonitor import diagnostics as diagnostics_platform
from custom_components.dessmonitor.const import DOMAIN


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

    assert report["device_info"]["serial_number"] == "SN-1"
    assert report["device_info"]["collector_pn"] == "PN-1"
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

    assert field["value"] == "Not Set"
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


async def test_a_diagnostic_sensor_matches_a_differently_spelled_title(
    hass: HomeAssistant,
) -> None:
    """The same case-sensitivity as #53, in the diagnostic sensor's lookup."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        "SN-1": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 6544, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": "Output  Priority", "val": "SBU", "unit": ""}],
        }
    }

    sensor = diagnostics_platform.DessMonitorDiagnosticSensor(
        coordinator=coordinator,
        device_sn="SN-1",
        device_meta=coordinator.data["SN-1"]["device"],
        collector_meta=coordinator.data["SN-1"]["collector"],
        sensor_key="Output priority",
        sensor_config=diagnostics_platform.DIAGNOSTIC_SENSORS["Output priority"],
    )

    assert sensor.native_value == "Solar → Battery → Utility"


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
