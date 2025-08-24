"""Device support module for DessMonitor integration.

This module provides devcode-specific mappings and transformations for different
data collector models. Each supported device type has its own configuration file.

To add support for a new devcode:
1. Create a new file: devcode_XXXX.py (e.g., devcode_2341.py)
2. Follow the template structure in devcode_2376.py
3. Import and register in device_registry.py
"""

from __future__ import annotations

from .device_registry import (
    apply_devcode_transformations,
    get_all_operating_modes,
    get_device_model_name,
    get_supported_devcodes,
    is_devcode_supported,
    map_charger_priority,
    map_operating_mode,
    map_output_priority,
    map_sensor_title,
)

__all__ = [
    "apply_devcode_transformations",
    "get_all_operating_modes",
    "get_device_model_name",
    "get_supported_devcodes",
    "is_devcode_supported",
    "map_charger_priority",
    "map_operating_mode",
    "map_output_priority",
    "map_sensor_title",
]
