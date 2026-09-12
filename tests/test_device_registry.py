"""Device transformation and unsupported-device warning contracts."""

from __future__ import annotations

import logging

import pytest

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    device_registry,
)


@pytest.fixture(autouse=True)
def reset_warning_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep process-wide warning history independent between tests."""
    monkeypatch.setattr(device_registry, "_WARNED_UNSUPPORTED_DEVCODES", set())


def test_unsupported_devcode_warning_explains_limitations_and_support(
    caplog: pytest.LogCaptureFixture,
) -> None:
    point = {"title": "Battery Voltage", "val": "53.2", "unit": "V"}

    with caplog.at_level(logging.WARNING):
        result = apply_devcode_transformations(6416, point)

    assert result == {"title": "Battery Voltage", "val": "53.2", "unit": "V"}
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "Unsupported devcode 6416" in message
    assert "device-specific mappings" in message
    assert "raw sensor titles and values" in message
    assert "limited" in message
    assert "request or add support" in message
    assert (
        "https://github.com/andreas-glaser/ha-dessmonitor/blob/dev/"
        "docs/ADDING_DEVCODES.md#request-support"
    ) in message


def test_unsupported_warning_is_once_per_devcode(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        for devcode in (6416, 9999, 6416, 9999):
            for title in ("Battery Voltage", "Output Voltage"):
                point = {"title": title, "val": "53.2"}
                assert apply_devcode_transformations(devcode, point) == point

    assert len(caplog.records) == 2
    assert "Unsupported devcode 6416" in caplog.records[0].getMessage()
    assert "Unsupported devcode 9999" in caplog.records[1].getMessage()


def test_supported_devcode_still_transforms_without_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    point = {"title": "Battery percentage", "val": "85", "unit": "%"}

    with caplog.at_level(logging.WARNING):
        result = apply_devcode_transformations(2376, point)

    assert result == {"title": "State of Charge", "val": "85", "unit": "%"}
    assert point == {"title": "Battery percentage", "val": "85", "unit": "%"}
    assert not caplog.records
