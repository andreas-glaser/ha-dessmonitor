"""Utility functions for DessMonitor integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


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
    firmware = collector_meta.get("fireware", "Unknown")

    if not device_alias:
        device_name = f"Inverter {collector_pn}"
    else:
        device_name = f"{device_alias} ({collector_pn})"

    return DeviceInfo(
        identifiers={(DOMAIN, device_sn)},
        name=device_name,
        manufacturer="DessMonitor",
        model="Energy Storage Inverter",
        sw_version=firmware,
        serial_number=device_sn,
    )
