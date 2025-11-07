"""Device registry for DessMonitor integration.

This module handles registration and lookup of all supported data collector types.
The devcode refers to the data collector/gateway device, not the inverter itself.
It automatically imports all devcode_*.py files and provides a unified interface.
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Registry of all supported devcodes
# This is populated by importing devcode modules below
_DEVICE_REGISTRY: dict[int, dict[str, Any]] = {}


def _register_devcode(devcode: int, config: dict[str, Any]) -> None:
    """Register a devcode configuration."""
    _DEVICE_REGISTRY[devcode] = config
    _LOGGER.debug("Registered devcode %s: %s", devcode, config["device_info"]["name"])


def _load_device_configurations() -> None:
    """Load all device configurations from devcode files."""
    try:
        # Import devcode 2376 configuration
        from .devcode_2376 import DEVCODE_CONFIG as config_2376

        _register_devcode(2376, config_2376)

        # Future devcode imports would go here:
        from .devcode_6422 import DEVCODE_CONFIG as config_6422

        _register_devcode(6422, config_6422)

    except ImportError as err:
        _LOGGER.error("Failed to import device configuration: %s", err)


# Load configurations on module import
_load_device_configurations()


def get_devcode_config(devcode: int) -> dict[str, Any] | None:
    """Get complete configuration for a devcode."""
    return _DEVICE_REGISTRY.get(devcode)


def get_supported_devcodes() -> list[int]:
    """Get list of all supported data collector codes."""
    return list(_DEVICE_REGISTRY.keys())


def is_devcode_supported(devcode: int) -> bool:
    """Check if a devcode is supported by the integration."""
    return devcode in _DEVICE_REGISTRY


def get_device_model_name(devcode: int) -> str:
    """Get human-readable data collector model name for a devcode."""
    config = get_devcode_config(devcode)
    if config:
        return config["device_info"]["name"]
    return f"Unsupported Device (devcode {devcode})"


def map_sensor_title(devcode: int, api_title: str) -> str:
    """Map API sensor title to standardized display name based on devcode."""
    config = get_devcode_config(devcode)
    if not config:
        _LOGGER.debug(
            "Unknown devcode %s, using original title: %s", devcode, api_title
        )
        return api_title

    # Get title mappings for this devcode
    title_mappings = config.get("sensor_title_mappings", {})

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
    config = get_devcode_config(devcode)
    if not config:
        return api_value

    priority_mappings = config.get("output_priority_mapping", {})
    return priority_mappings.get(api_value, api_value)


def map_charger_priority(devcode: int, api_value: str) -> str:
    """Map charger priority value to human-readable format based on devcode."""
    config = get_devcode_config(devcode)
    if not config:
        return api_value

    charger_mappings = config.get("charger_priority_mapping", {})
    return charger_mappings.get(api_value, api_value)


def map_operating_mode(devcode: int, api_value: str) -> str:
    """Map operating mode value to human-readable format based on devcode."""
    config = get_devcode_config(devcode)
    if not config:
        return api_value

    mode_mappings = config.get("operating_mode_mapping", {})
    if not isinstance(api_value, str):
        return api_value

    normalized_value = api_value.strip()

    if normalized_value in mode_mappings:
        mapped = mode_mappings[normalized_value]
        _LOGGER.debug(
            "Operating mode map (devcode %s): '%s' -> '%s'",
            devcode,
            api_value,
            mapped,
        )
        return mapped

    for candidate, mapped_value in mode_mappings.items():
        if (
            isinstance(candidate, str)
            and candidate.lower().strip() == normalized_value.lower()
        ):
            _LOGGER.debug(
                "Operating mode map (devcode %s - case-insensitive): '%s' -> '%s'",
                devcode,
                api_value,
                mapped_value,
            )
            return mapped_value

    _LOGGER.debug(
        "Operating mode map (devcode %s): '%s' -> '%s' (no mapping)",
        devcode,
        api_value,
        normalized_value,
    )
    return normalized_value


def apply_devcode_transformations(
    devcode: int, sensor_data: dict[str, Any]
) -> dict[str, Any]:
    """Apply all devcode-specific transformations to sensor data."""
    if not is_devcode_supported(devcode):
        _LOGGER.warning("Unsupported devcode %s - no transformations applied", devcode)
        return sensor_data

    config = get_devcode_config(devcode)
    if not config:
        return sensor_data

    transformed_data = sensor_data.copy()

    _apply_title_mapping(devcode, transformed_data)
    _apply_value_mappings(devcode, transformed_data)
    _apply_custom_transformations(config, transformed_data)

    return transformed_data


def _apply_title_mapping(devcode: int, transformed_data: dict[str, Any]) -> None:
    """Map sensor title to configured alias when available."""
    if "title" not in transformed_data:
        return

    original_title = transformed_data["title"]
    transformed_data["title"] = map_sensor_title(devcode, original_title)


def _apply_value_mappings(devcode: int, transformed_data: dict[str, Any]) -> None:
    """Apply built-in value mappings such as priorities and modes."""
    title = transformed_data.get("title")
    value = transformed_data.get("val")
    if title is None or value is None:
        return

    normalized = title.lower()
    if "priority" in normalized and "output" in normalized:
        transformed_data["val"] = map_output_priority(devcode, str(value))
    elif "priority" in normalized and "charg" in normalized:
        transformed_data["val"] = map_charger_priority(devcode, str(value))
    elif "operating mode" in normalized or normalized.endswith(" mode"):
        transformed_data["val"] = map_operating_mode(devcode, str(value))


def _apply_custom_transformations(
    config: dict[str, Any], transformed_data: dict[str, Any]
) -> None:
    """Apply custom transformation callbacks defined by the devcode config."""
    title = transformed_data.get("title")
    if not title:
        return

    value_transformations = config.get("value_transformations", {})
    transform_func = value_transformations.get(title)
    if not transform_func:
        return

    try:
        transformed_data["val"] = transform_func(transformed_data.get("val"))
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Value transformation failed for %s: %s",
            title,
            err,
        )


def get_device_capabilities(devcode: int) -> list[str]:
    """Get list of supported features for a devcode."""
    config = get_devcode_config(devcode)
    if config:
        return config["device_info"].get("supported_features", [])
    return []


def get_all_operating_modes() -> list[str]:
    """Get all possible operating mode values from base modes and all devcode transformations."""
    from ..const import OPERATING_MODES

    # Start with base operating modes
    all_modes = set(OPERATING_MODES)

    # Add transformed values from all registered devcodes
    for devcode, config in _DEVICE_REGISTRY.items():
        operating_mode_mapping = config.get("operating_mode_mapping", {})
        # Add both original API values and transformed values
        all_modes.update(operating_mode_mapping.keys())
        all_modes.update(operating_mode_mapping.values())

    return sorted(all_modes)


def get_registry_info() -> dict[str, Any]:
    """Get information about all registered devices."""
    return {
        "supported_devcodes": get_supported_devcodes(),
        "total_devices": len(_DEVICE_REGISTRY),
        "devices": {
            devcode: {
                "name": config["device_info"]["name"],
                "description": config["device_info"].get("description", ""),
                "features": config["device_info"].get("supported_features", []),
            }
            for devcode, config in _DEVICE_REGISTRY.items()
        },
    }
