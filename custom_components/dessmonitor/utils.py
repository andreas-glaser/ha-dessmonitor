"""Utility functions for DessMonitor integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def create_device_info(
    device_sn: str,
    device_meta: dict[str, Any],
    collector_meta: dict[str, Any],
) -> DeviceInfo:
    """Create device info dictionary for a DessMonitor device.

    Args:
        device_sn: The device serial number
        device_meta: Device metadata from API
        collector_meta: Collector metadata from API

    Returns:
        DeviceInfo dictionary for Home Assistant
    """
    collector_pn = collector_meta.get("pn", "Unknown")
    device_alias = device_meta.get("alias")
    firmware = device_meta.get("firmware") or collector_meta.get("fireware", "Unknown")
    is_local = device_meta.get("connection_type") == "local"

    if not device_alias:
        device_name = f"Inverter {collector_pn}"
    else:
        device_name = f"{device_alias} ({collector_pn})"

    return DeviceInfo(
        identifiers={(DOMAIN, device_sn)},
        name=device_name,
        manufacturer="Local inverter" if is_local else "DessMonitor",
        model=device_meta.get("model", "Energy Storage Inverter"),
        sw_version=firmware,
        serial_number=device_sn,
    )


def control_entity_suffix(name: str) -> str:
    """Build the unique-id suffix a control entity is registered under."""
    return name.lower().replace(" ", "_").replace("-", "_")


def async_migrate_control_unique_ids(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    platform: str,
    entities: Iterable[Any],
) -> None:
    """Carry renamed control entities over to their current unique id.

    A control entity is identified by the name the vendor reports for the
    field, so giving a devcode a control name mapping, or trimming a name the
    vendor padded with whitespace, changes that identity. Without this the
    existing entity would be stranded in the registry and a second one would
    appear beside it, breaking every automation that referenced the first.
    """
    registry = er.async_get(hass)
    for entity in entities:
        legacy_id = getattr(entity, "legacy_unique_id", None)
        current_id = entity.unique_id
        if not legacy_id or not current_id or legacy_id == current_id:
            continue

        entity_id = registry.async_get_entity_id(platform, DOMAIN, legacy_id)
        if entity_id is None:
            continue
        entry = registry.async_get(entity_id)
        if entry is None or entry.config_entry_id != config_entry.entry_id:
            continue
        if registry.async_get_entity_id(platform, DOMAIN, current_id) is not None:
            _LOGGER.debug(
                "Not migrating %s to %s: that unique id is already registered",
                entity_id,
                current_id,
            )
            continue

        registry.async_update_entity(entity_id, new_unique_id=current_id)
        _LOGGER.info("Migrated %s from %s to %s", entity_id, legacy_id, current_id)
