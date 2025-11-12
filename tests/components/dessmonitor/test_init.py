"""Integration-level tests for async_setup_entry."""

import pytest

from custom_components.dessmonitor.const import DOMAIN


@pytest.mark.ha_integration
async def test_setup_entry_creates_expected_entities(
    hass, mock_config_entry, patch_api, enable_custom_integrations
):
    """Ensure the mocked payload produces core sensors."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    operating_mode = hass.states.get("sensor.inverter_1_operating_mode")
    assert operating_mode is not None
    assert operating_mode.state == "Grid Mode"

    energy_today = hass.states.get("sensor.inverter_1_energy_today")
    assert energy_today is not None
    assert energy_today.state == "12.5"


@pytest.mark.ha_integration
async def test_unload_entry_cleans_up_coordinator(
    hass, mock_config_entry, patch_api, enable_custom_integrations
):
    """Unloading the entry should remove stored data."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert DOMAIN in hass.data and mock_config_entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})
