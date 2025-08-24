"""Device-specific mappings and value transformations for DessMonitor integration."""

from __future__ import annotations

import logging
from typing import Any

from .const import DEVCODE_MAPPINGS

_LOGGER = logging.getLogger(__name__)


def get_devcode_info(devcode: int) -> dict[str, Any] | None:
    """Get device information for a specific devcode."""
    return DEVCODE_MAPPINGS.get(devcode)


def get_supported_devcodes() -> list[int]:
    """Get list of supported device codes."""
    return list(DEVCODE_MAPPINGS.keys())


def map_sensor_title(devcode: int, api_title: str) -> str:
    """Map API sensor title to standardized display name based on devcode."""
    devcode_info = get_devcode_info(devcode)
    if not devcode_info:
        _LOGGER.debug(
            "Unknown devcode %s, using original title: %s", devcode, api_title
        )
        return api_title

    # Get title mappings for this devcode
    title_mappings = devcode_info.get("sensor_title_mappings", {})

    # Apply mapping if exists, otherwise use original
    mapped_title = title_mappings.get(api_title, api_title)

    if mapped_title != api_title:
        _LOGGER.debug(
            "Mapped sensor title for devcode %s: %s → %s",
            devcode,
            api_title,
            mapped_title,
        )

    return mapped_title


def map_output_priority(devcode: int, api_value: str) -> str:
    """Map output priority value to human-readable format based on devcode."""
    devcode_info = get_devcode_info(devcode)
    if not devcode_info:
        return api_value

    priority_mappings = devcode_info.get("output_priority_mapping", {})
    return priority_mappings.get(api_value, api_value)


def map_charger_priority(devcode: int, api_value: str) -> str:
    """Map charger priority value to human-readable format based on devcode."""
    devcode_info = get_devcode_info(devcode)
    if not devcode_info:
        return api_value

    charger_mappings = devcode_info.get("charger_priority_mapping", {})
    return charger_mappings.get(api_value, api_value)


def map_operating_mode(devcode: int, api_value: str) -> str:
    """Map operating mode value to human-readable format based on devcode."""
    devcode_info = get_devcode_info(devcode)
    if not devcode_info:
        return api_value

    mode_mappings = devcode_info.get("operating_mode_mapping", {})
    return mode_mappings.get(api_value, api_value)


def is_devcode_supported(devcode: int) -> bool:
    """Check if a devcode is supported by the integration."""
    return devcode in DEVCODE_MAPPINGS


def get_device_model_name(devcode: int) -> str:
    """Get human-readable device model name for a devcode."""
    devcode_info = get_devcode_info(devcode)
    if devcode_info:
        return devcode_info.get("name", f"Unknown Device (devcode {devcode})")
    return f"Unsupported Device (devcode {devcode})"


def apply_devcode_transformations(
    devcode: int, sensor_data: dict[str, Any]
) -> dict[str, Any]:
    """Apply all devcode-specific transformations to sensor data."""
    if not is_devcode_supported(devcode):
        _LOGGER.warning("Unsupported devcode %s - no transformations applied", devcode)
        return sensor_data

    transformed_data = sensor_data.copy()

    # Apply title mapping
    if "title" in transformed_data:
        original_title = transformed_data["title"]
        transformed_data["title"] = map_sensor_title(devcode, original_title)

    # Apply value mappings for specific sensor types
    if "title" in transformed_data and "val" in transformed_data:
        title = transformed_data["title"]
        value = transformed_data["val"]

        if "priority" in title.lower() and "output" in title.lower():
            transformed_data["val"] = map_output_priority(devcode, str(value))
        elif "priority" in title.lower() and "charg" in title.lower():
            transformed_data["val"] = map_charger_priority(devcode, str(value))
        elif "operating mode" in title.lower() or "mode" in title.lower():
            transformed_data["val"] = map_operating_mode(devcode, str(value))

    return transformed_data
