"""The diagnostics platform Home Assistant reads its hooks from.

Both hooks delegate to the builders in ``__init__``. Nothing else belongs here:
``diagnostics`` is not an entity platform, so a sensor defined in this module
is never created, which is how two diagnostic sensors sat here unused until
#60.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Expose the device diagnostics builder on the module Home Assistant loads.

    Home Assistant reads these functions off the integration's ``diagnostics``
    platform, so the implementation in ``__init__`` was never reachable and the
    download button did nothing. The import is deferred to keep this module
    free of an import cycle at load time.
    """
    from . import async_get_device_diagnostics as build_device_diagnostics

    return await build_device_diagnostics(hass, entry, device)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Expose the hub diagnostics builder on the module Home Assistant loads.

    Only the device hook existed, so "Download diagnostics" on the integration
    card asked for a config-entry report the integration never offered and the
    request failed before it reached us. Defining this anywhere but here would
    leave it just as dead.
    """
    from . import async_get_config_entry_diagnostics as build_entry_diagnostics

    return await build_entry_diagnostics(hass, entry)
