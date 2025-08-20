"""The DessMonitor integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DessMonitorAPI
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DessMonitor from a config entry."""
    _LOGGER.debug("Setting up DessMonitor integration for entry: %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})
    
    username = entry.data["username"]
    company_key = entry.data.get("company_key", "bnrl_frRFjEz8Mkn")
    _LOGGER.debug("Initializing API client for user: %s with company key: %s", username, company_key)
    
    api = DessMonitorAPI(
        username=username,
        password=entry.data["password"],
        company_key=company_key,
    )
    
    try:
        _LOGGER.debug("Attempting initial authentication")
        await api.authenticate()
        _LOGGER.info("Initial authentication successful for DessMonitor integration")
    except Exception as err:
        _LOGGER.error("Failed to authenticate with DessMonitor API during setup: %s", err)
        _LOGGER.debug("Authentication setup error details", exc_info=True)
        return False
    
    update_interval = entry.options.get(
        CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    )
    _LOGGER.debug("Using update interval: %d seconds", update_interval)
    
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, update_interval)
    _LOGGER.debug("Created data update coordinator, performing first refresh")
    
    try:
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("First data refresh completed successfully")
    except Exception as err:
        _LOGGER.error("Failed to perform initial data refresh: %s", err)
        _LOGGER.debug("Initial refresh error details", exc_info=True)
        return False
        
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("DessMonitor integration setup completed successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading DessMonitor integration entry: %s", entry.entry_id)
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Coordinator removed and platforms unloaded successfully")
        
        # Close API session if it exists
        if hasattr(coordinator, 'api') and hasattr(coordinator.api, 'close'):
            try:
                await coordinator.api.close()
                _LOGGER.debug("API session closed successfully")
            except Exception as err:
                _LOGGER.warning("Error closing API session: %s", err)
    else:
        _LOGGER.error("Failed to unload platforms for entry: %s", entry.entry_id)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.info("Reloading DessMonitor integration due to configuration changes")
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


class DessMonitorDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the DessMonitor API."""
    
    def __init__(self, hass: HomeAssistant, api: DessMonitorAPI, update_interval: int) -> None:
        """Initialize."""
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
    
    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Starting data update cycle")
        try:
            data = {}
            _LOGGER.debug("Fetching collectors list")
            collectors = await self.api.get_collectors()
            _LOGGER.debug("Found %d collectors to process", len(collectors))
            
            for i, collector in enumerate(collectors):
                collector_id = collector["pn"]
                _LOGGER.debug("Processing collector %d/%d: %s", i + 1, len(collectors), collector_id)
                
                devices = await self.api.get_collector_devices(collector_id)
                device_list = devices.get("dev", [])
                _LOGGER.debug("Collector %s has %d devices", collector_id, len(device_list))
                
                for j, device in enumerate(device_list):
                    device_sn = device["sn"]
                    _LOGGER.debug("Processing device %d/%d: %s (devcode=%s, devaddr=%s)", 
                                j + 1, len(device_list), device_sn, device["devcode"], device["devaddr"])
                    
                    device_data = await self.api.get_device_last_data(
                        pn=collector_id,
                        devcode=device["devcode"],
                        devaddr=device["devaddr"],
                        sn=device_sn
                    )
                    
                    data[device_sn] = {
                        "collector": collector,
                        "device": device,
                        "data": device_data
                    }
                    _LOGGER.debug("Stored data for device %s with %d data points", device_sn, len(device_data))
            
            _LOGGER.info("Data update completed successfully: %d devices total", len(data))
            return data
            
        except Exception as err:
            _LOGGER.error("Error communicating with DessMonitor API during update: %s", err)
            _LOGGER.debug("Data update error details", exc_info=True)
            raise

