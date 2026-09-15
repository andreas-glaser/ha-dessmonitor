"""Parameter-backed sensors from cloud fetch through entity discovery.

Exercise the existing 2376 support and the 6514 regression from issue #35
through the same contract. Only the cloud API boundary is mocked.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
from custom_components.dessmonitor.api import DessMonitorAPI, DessMonitorError
from custom_components.dessmonitor.sensor import _build_sensor_entities


@pytest.fixture(params=[2376, 6514], ids=["existing-2376", "anenji-6514"])
def device(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Collectors known to expose Battery percentage through parameters."""
    return {"sn": "TEST-INVERTER", "devcode": request.param, "devaddr": 1}


@pytest.fixture
def cloud_api() -> MagicMock:
    """Keep cloud calls isolated while enforcing the real client's interface."""
    api = create_autospec(DessMonitorAPI, instance=True)
    api.get_device_last_data.return_value = [
        {"title": "Battery Voltage", "val": "53.3", "unit": "V"}
    ]
    return api


@pytest.fixture
async def coordinator(
    hass: HomeAssistant, cloud_api: MagicMock
) -> AsyncGenerator[DessMonitorDataUpdateCoordinator, None]:
    """Use the real coordinator and always release its resources."""
    instance = DessMonitorDataUpdateCoordinator(hass, cloud_api, 300)
    try:
        yield instance
    finally:
        await instance.async_shutdown()


@pytest.mark.parametrize(
    ("parameter_value", "existing_title", "expected_soc"),
    [
        ("85", None, 85),
        ("0", None, 0),
        ("85", "Battery percentage", 90),
        ("85", "State of Charge", 90),
    ],
    ids=["reported-soc", "empty-battery", "raw-title-present", "mapped-title-present"],
)
async def test_parameter_soc_becomes_sensor_without_duplicates(
    coordinator: DessMonitorDataUpdateCoordinator,
    cloud_api: MagicMock,
    device: dict[str, Any],
    parameter_value: str,
    existing_title: str | None,
    expected_soc: int,
) -> None:
    """Fetch parameter SOC, preserving any reading already in latest data."""
    if existing_title:
        cloud_api.get_device_last_data.return_value.append(
            {"title": existing_title, "val": "90", "unit": "%"}
        )
    # Parameter name, ID, unit, and reported 85% value from analysis_6514.json.
    cloud_api.get_device_parameters.return_value = {
        "Battery percentage": {
            "value": parameter_value,
            "unit": "%",
            "id": "bt_battery_capacity",
        },
        "Battery Voltage": {"value": "53.3", "unit": "V"},
    }

    points = await coordinator._fetch_device_data(
        "TEST-COLLECTOR", device, device["devcode"]
    )
    coordinator.async_set_updated_data(
        {
            device["sn"]: {
                "collector": {"pn": "TEST-COLLECTOR"},
                "device": device,
                "data": points,
            }
        }
    )
    known_sensors: set[str] = set()
    entities = _build_sensor_entities(coordinator, known_sensors)
    soc = [
        entity
        for entity in entities
        if entity.unique_id == "TEST-INVERTER_state_of_charge"
    ]

    assert len(soc) == 1
    assert soc[0].native_value == expected_soc
    assert soc[0].native_unit_of_measurement == "%"
    assert len(points) == 2
    assert _build_sensor_entities(coordinator, known_sensors) == []
    cloud_api.get_device_parameters.assert_awaited_once_with(
        pn="TEST-COLLECTOR", devcode=device["devcode"], devaddr=1, sn="TEST-INVERTER"
    )


@pytest.mark.parametrize("parameters_fail", [False, True], ids=["missing", "api-error"])
async def test_unavailable_parameters_preserve_primary_telemetry(
    coordinator: DessMonitorDataUpdateCoordinator,
    cloud_api: MagicMock,
    device: dict[str, Any],
    parameters_fail: bool,
) -> None:
    """An optional SOC fetch must neither fabricate data nor block telemetry."""
    cloud_api.get_device_parameters.return_value = {}
    if parameters_fail:
        cloud_api.get_device_parameters.side_effect = DessMonitorError("Offline")

    points = await coordinator._fetch_device_data(
        "TEST-COLLECTOR", device, device["devcode"]
    )

    assert points == [{"title": "Battery Voltage", "val": "53.3", "unit": "V"}]
    cloud_api.get_device_parameters.assert_awaited_once()
