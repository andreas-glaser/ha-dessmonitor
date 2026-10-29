"""Home Assistant reads diagnostics off the integration's diagnostics module."""

from __future__ import annotations

from unittest.mock import MagicMock

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
