"""What a diagnostics download says about local control.

This section is the evidence two different jobs depend on. A failed write is
diagnosed from the recorded outcomes, and a devcode profile's
``local_control_settings`` is declared from the pairing report - which is the
only thing that connects a cloud control's field id to the local setting that
writes the same register.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.dessmonitor import diagnostics as diagnostics_platform
from custom_components.dessmonitor.const import (
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_CONTROL,
    CONNECTION_TYPE_LOCAL,
    DOMAIN,
    LOCAL_CONTROL_ENABLED,
)
from custom_components.dessmonitor.local.writer import SettingsSnapshot, WriteOutcome
from custom_components.dessmonitor.local.settings import pairing_candidates

SERIAL = "SN-LOCAL"


def _snapshot(values: dict[str, str] | None = None) -> SettingsSnapshot:
    """Build a PI18 snapshot the way the backend builds one."""
    from custom_components.dessmonitor.local.p17_settings import settings_for

    ratings = (
        "2300,217,2300,500,217,5000,5000,480,500,540,450,560,540,2,010,060,1,1,1,"
        "9,1,0,0,0,1,00"
    ).split(",")
    enumerations = {"MCHGCR": ("010", "060"), "MUCHGCR": ("002", "010")}
    settings = settings_for(tuple(ratings))
    reported = {
        setting.key: decoded
        for setting in settings
        if (decoded := setting.decode(ratings[setting.index], enumerations)) is not None
    }
    reported.update(values or {})
    return SettingsSnapshot(settings, reported, enumerations, ("battery_type",))


def _local_coordinator(snapshot: SettingsSnapshot | None = None) -> MagicMock:
    """A local coordinator surface, as the diagnostics builder reads it."""
    coordinator = MagicMock()
    coordinator.is_local = True
    coordinator.is_hybrid = False
    coordinator.control_enabled = True
    coordinator.driver_key = "p17"
    coordinator.data = {
        SERIAL: {
            "collector": {"pn": "PN-LOCAL", "fireware": "Local"},
            "device": {
                "devcode": 2452,
                "devaddr": 1,
                "alias": "Local Inverter 1",
                "connection_type": "local",
            },
            "data": [{"title": "Battery Voltage", "val": 54.4, "unit": "V"}],
        }
    }
    coordinator.settings_snapshot = lambda serial: (
        snapshot if serial == SERIAL else None
    )
    coordinator.settings_error = lambda _serial: None
    coordinator.write_history = lambda _serial: [
        WriteOutcome(
            key="battery_bulk_voltage",
            command="MCHGV",
            requested="57.0",
            acknowledged=True,
            verified=True,
            reported="57.0",
            elapsed_ms=120,
        ).as_dict()
    ]
    # A local entry keeps no cloud summary bookkeeping at all.
    del coordinator.summary_points_not_merged
    return coordinator


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry-local"
    entry.data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL}
    entry.options = {CONF_LOCAL_CONTROL: LOCAL_CONTROL_ENABLED}
    return entry


async def test_a_local_entry_can_download_diagnostics_at_all(
    hass: HomeAssistant,
) -> None:
    """The regression that made the button fail on exactly the wrong entries.

    Both diagnostics hooks reached for the cloud summary bookkeeping without
    checking, and a local-only entry has none, so "Download diagnostics"
    raised - on the entries whose owners are asked for a download most often.
    """
    coordinator = _local_coordinator(_snapshot())
    hass.data[DOMAIN] = {"entry-local": coordinator}

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, _entry(), DeviceEntry(identifiers={(DOMAIN, SERIAL)})
    )

    assert report["device_info"]["device_code"] == 2452
    assert report["raw_data_points"] == 1


async def test_the_download_reports_what_the_inverter_says_it_can_write(
    hass: HomeAssistant,
) -> None:
    """Reported settings, accepted limits, and the ones it did not report."""
    coordinator = _local_coordinator(_snapshot())
    hass.data[DOMAIN] = {"entry-local": coordinator}

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, _entry(), DeviceEntry(identifiers={(DOMAIN, SERIAL)})
    )
    local = report["local_control"]

    assert local["enabled"] is True
    assert local["protocol"] == "p17"
    assert local["reported"]["battery_bulk_voltage"] == "56.0"
    assert local["not_reported"] == ["battery_type"]
    assert local["accepted_values"]["MCHGCR"] == ["010", "060"]
    assert local["writes"][-1]["verified"] is True
    assert local["writes"][-1]["command"] == "MCHGV"
    # Nothing identifying is added by this section.
    assert SERIAL not in json.dumps(report)


async def test_a_read_only_entry_says_so_and_nothing_more(
    hass: HomeAssistant,
) -> None:
    """With the option off there is no settings block to report."""
    coordinator = _local_coordinator(None)
    coordinator.control_enabled = False
    hass.data[DOMAIN] = {"entry-local": coordinator}

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, _entry(), DeviceEntry(identifiers={(DOMAIN, SERIAL)})
    )

    assert report["local_control"] == {"enabled": False}


async def test_a_failed_settings_read_is_reported_as_the_reason(
    hass: HomeAssistant,
) -> None:
    """An inverter that did not answer is distinguished from one turned off."""
    coordinator = _local_coordinator(None)
    coordinator.settings_error = lambda _serial: "PIRI timed out"
    hass.data[DOMAIN] = {"entry-local": coordinator}

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, _entry(), DeviceEntry(identifiers={(DOMAIN, SERIAL)})
    )

    assert report["local_control"] == {"enabled": True, "error": "PIRI timed out"}


async def test_a_cloud_entry_has_no_local_control_section(
    hass: HomeAssistant,
) -> None:
    """A cloud-only entry's download is unchanged by any of this."""
    coordinator = MagicMock()
    coordinator.is_local = False
    coordinator.summary_points_not_merged = {}
    coordinator.data = {
        "SN-CLOUD": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 6544, "devaddr": 1, "alias": "Inverter"},
            "data": [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}],
        }
    }
    coordinator.api.get_device_control_fields = AsyncMock(return_value={})
    coordinator.api.get_device_parameters = AsyncMock(return_value={})
    entry = MagicMock(entry_id="entry-cloud", data={}, options={})
    hass.data[DOMAIN] = {"entry-cloud": coordinator}

    report = await diagnostics_platform.async_get_device_diagnostics(
        hass, entry, DeviceEntry(identifiers={(DOMAIN, "SN-CLOUD")})
    )

    assert "local_control" not in report


def test_the_pairing_report_names_the_control_a_setting_matches() -> None:
    """A name that normalises to the same string is reported as the pairing.

    This is what the hybrid coordinator pairs on, so the download shows an
    owner's maintainer exactly which controls will take the local link.
    """
    snapshot = _snapshot()
    controls = {
        "Battery Bulk Voltage": {"id": "bse_bulk", "type": "value"},
        "Bulk Charging Voltage": {"id": "vendor_bulk", "type": "value"},
    }
    values = {"bse_bulk": "56.0", "vendor_bulk": "56.0"}

    report = {
        item["setting"]: item
        for item in pairing_candidates(
            snapshot.settings, snapshot.values, controls, values
        )
    }

    bulk = report["battery_bulk_voltage"]
    assert bulk["paired_by_name"] == "bse_bulk"
    assert bulk["reported"] == "56.0"
    assert bulk["command"] == "MCHGV"
    # The vendor's own spelling is a candidate, because the figures agree, and
    # a candidate is not a declaration.
    candidates = {item["control"]: item for item in bulk["candidates"]}
    assert candidates["Bulk Charging Voltage"]["name_matches"] is False
    assert candidates["Battery Bulk Voltage"]["name_matches"] is True


def test_the_pairing_report_does_not_pair_a_selection_by_its_code() -> None:
    """Every one of these selections reads 0, 1 or 2, so agreement proves nothing."""
    snapshot = _snapshot()
    controls = {"Some Other Control": {"id": "other", "type": "options"}}

    report = {
        item["setting"]: item
        for item in pairing_candidates(
            snapshot.settings, snapshot.values, controls, {"other": "1"}
        )
    }

    assert report["output_source_priority"]["reported"] == "1"
    assert report["output_source_priority"]["candidates"] == []


def test_a_setting_with_no_cloud_counterpart_is_still_listed() -> None:
    """The report covers every setting, so a missing pairing is visible."""
    snapshot = _snapshot()

    report = pairing_candidates(snapshot.settings, snapshot.values, {}, {})

    assert {item["setting"] for item in report} >= set(snapshot.values)
    assert all(item["candidates"] == [] for item in report)


async def test_a_hybrid_entry_reports_the_paired_local_inverter(
    hass: HomeAssistant,
) -> None:
    """The section describes the inverter the readings are coming from.

    A hybrid entry's cloud serial and local serial are usually different
    strings, and the pairing reuses the telemetry overlay's own matching, so
    the settings reported here belong to the inverter whose measurements are
    published under this device.
    """
    from unittest.mock import patch

    from custom_components.dessmonitor.const import (
        CONF_LOCAL_COLLECTOR_IP,
        CONF_LOCAL_LISTEN_IP,
        CONF_LOCAL_TCP_PORT,
        CONF_LOCAL_UDP_PORT,
    )
    from custom_components.dessmonitor.local.hybrid import DessMonitorHybridCoordinator

    api = MagicMock(token="token", secret="secret", close=AsyncMock())
    api.get_device_control_fields = AsyncMock(
        return_value={"Battery Bulk Voltage": {"id": "bse_bulk", "type": "value"}}
    )
    api.get_device_parameters = AsyncMock(return_value={})
    coordinator = DessMonitorHybridCoordinator(
        hass,
        api,
        300,
        {
            CONF_LOCAL_LISTEN_IP: "127.0.0.1",
            CONF_LOCAL_COLLECTOR_IP: "127.0.0.2",
            CONF_LOCAL_TCP_PORT: 0,
            CONF_LOCAL_UDP_PORT: 9,
            CONF_LOCAL_CONTROL: LOCAL_CONTROL_ENABLED,
        },
        "entry-hybrid",
    )
    coordinator.data = {
        "CLOUD-SN": {
            "collector": {"pn": "PN-1"},
            "device": {"devcode": 2452, "devaddr": 1, "alias": "Main"},
            "data": [{"title": "Battery Voltage", "val": 54.4, "unit": "V"}],
        }
    }
    local = coordinator.locals[0]
    local.async_set_updated_data(
        {
            "LOCAL-SN": {
                "collector": {"pn": "PN-1"},
                "device": {"devcode": 2452, "devaddr": 1},
                "data": [],
            }
        }
    )
    local._settings["LOCAL-SN"] = _snapshot()
    hass.data[DOMAIN] = {"entry-hybrid": coordinator}
    entry = MagicMock(entry_id="entry-hybrid", data={}, options={})

    try:
        report = await diagnostics_platform.async_get_device_diagnostics(
            hass, entry, DeviceEntry(identifiers={(DOMAIN, "CLOUD-SN")})
        )
    finally:
        await coordinator.async_shutdown()

    local_control = report["local_control"]
    assert local_control["enabled"] is True
    assert local_control["reported"]["battery_bulk_voltage"] == "56.0"
    # The cloud control that will take the local link is named here, which is
    # what a maintainer declares in the devcode profile.
    pairing = {item["setting"]: item for item in local_control["cloud_pairing"]}
    assert pairing["battery_bulk_voltage"]["paired_by_name"] == "bse_bulk"
