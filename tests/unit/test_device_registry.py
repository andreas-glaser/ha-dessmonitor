"""Tests for the devcode registry helpers."""

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    device_registry,
)


def test_map_operating_mode_handles_spelling_variant():
    """Ensure SRNE 'Inverter Operation' maps to Off-grid Mode."""
    mapped = device_registry.map_operating_mode(2361, "Inverter Operation")
    assert mapped == "Off-grid Mode"


def test_sensor_title_mapping_applies_known_alias():
    """Known SRNE aliases should be normalized before entity creation."""
    data_point = {"title": "Battery level SOC", "val": 77}
    transformed = apply_devcode_transformations(2361, data_point)
    assert transformed["title"] == "State of Charge"
    assert transformed["val"] == 77


def test_supported_devcodes_contains_known_entries():
    """Registry should expose all currently supported devcodes."""
    supported = device_registry.get_supported_devcodes()
    assert 2361 in supported
    assert 2376 in supported
    assert 6422 in supported
