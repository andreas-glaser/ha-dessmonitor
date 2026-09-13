"""Devcode 518 title mapping, against a sanitized API response.

Without this mapping the energy and power sensors of a grid-tie PV inverter sit
at 0 while the data is present in the payload, because devcode 518 reports
lower-cased, spelled-out titles that do not match the canonical sensor names.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
from custom_components.dessmonitor.api import DessMonitorAPI
from custom_components.dessmonitor.const import DOMAIN, SENSOR_TYPES
from custom_components.dessmonitor.device_support.device_registry import (
    get_device_model_name,
    map_sensor_title,
)
from custom_components.dessmonitor.sensor import async_setup_entry

FIXTURE = Path(__file__).parent / "fixtures" / "devcode_518_query_device_last_data.json"
DEVCODE = 518


def _titles() -> list[str]:
    with FIXTURE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return [entry["title"] for entry in payload["dat"]]


def test_fixture_carries_no_account_identifiers() -> None:
    """The fixture must stay safe to ship in the repository."""
    raw = FIXTURE.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert isinstance(payload["dat"], list)
    assert all(set(point) == {"title", "unit", "val"} for point in payload["dat"])
    for leaky in ("token", "sign=", "salt=", "secret"):
        assert leaky not in raw


def test_the_device_is_recognised() -> None:
    assert "518" in get_device_model_name(DEVCODE)


def test_energy_and_power_titles_map_to_canonical_names() -> None:
    """These four are the ones that used to read 0."""
    assert map_sensor_title(DEVCODE, "active power") == "Output Active Power"
    assert map_sensor_title(DEVCODE, "DC output power") == "PV Power"
    assert map_sensor_title(DEVCODE, "total energy") == "Energy Total"
    assert map_sensor_title(DEVCODE, "today energy") == "Energy Today"


def test_every_mapped_title_resolves_to_a_known_sensor() -> None:
    """A mapping that points at a name the integration does not know is dead."""
    for title in _titles():
        mapped = map_sensor_title(DEVCODE, title)
        if mapped != title:
            assert mapped in SENSOR_TYPES, f"{title!r} maps to unknown {mapped!r}"


def test_unmapped_titles_pass_through_unchanged() -> None:
    """Case-insensitive sensor lookup handles unmapped grid voltage."""
    assert map_sensor_title(DEVCODE, "grid voltage") == "grid voltage"


def test_other_devcodes_are_untouched_by_this_mapping() -> None:
    """The 518 table must not leak into devices that report the same titles."""
    assert map_sensor_title(2376, "active power") == "active power"


async def test_fixture_through_api_and_sensor_platform(cloud_transport):
    payload = json.loads(
        (
            Path(__file__).parent / "fixtures/devcode_518_query_device_last_data.json"
        ).read_text()
    )
    session, connector = cloud_transport
    connector.payload = payload
    api = DessMonitorAPI(
        "test-user", "test-password", session=session, api_profile="shinemonitor_solar"
    )
    api.token, api.secret = "test-token", "test-secret"
    points = await api.get_device_last_data("REDACTED-PN", 518, 1, "REDACTED-SN")
    coordinator = MagicMock()
    coordinator.data = {
        "REDACTED-SN": {
            "collector": {"pn": "REDACTED-PN"},
            "device": {"devcode": 518, "devaddr": 1},
            "data": points,
        }
    }
    hass = MagicMock()
    hass.data = {DOMAIN: {"entry": coordinator}}
    added = MagicMock()
    await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
    entities = {entity.unique_id: entity for entity in added.call_args.args[0]}
    assert entities["REDACTED-SN_pv_power"].native_value == 1902
    assert entities["REDACTED-SN_energy_total"].native_value == 10468.9
    assert entities["REDACTED-SN_grid_voltage"].native_value == 223.6
    apparent_power = entities["REDACTED-SN_output_apparent_power"]
    assert apparent_power.native_value == 1871
    assert apparent_power.native_unit_of_measurement == "VA"
    assert apparent_power.device_class == "apparent_power"
    assert len(entities) == 13


async def test_solar_refresh_does_not_create_duplicate_energy_sensors(
    hass, cloud_transport
):
    points = json.loads(
        (
            Path(__file__).parent / "fixtures/devcode_518_query_device_last_data.json"
        ).read_text()
    )["dat"]
    routes = {
        "queryPlants": {"plant": [{"pid": 1}]},
        "webQueryCollectorsEs": {
            "collector": [{"pn": "REDACTED-PN", "pid": 1}],
            "total": 1,
        },
        "queryCollectorDevices": {
            "dev": [{"sn": "REDACTED-SN", "devcode": 518, "devaddr": 1}]
        },
        "queryDeviceLastData": points,
        "webQueryDeviceEs": {
            "device": [
                {
                    "sn": "REDACTED-SN",
                    "outpower": 1.834,
                    "energyToday": 12.7,
                    "energyTotal": 10468.9,
                }
            ]
        },
    }

    def respond(request):
        target = request.split(b"\r\n", 1)[0].decode().split(" ")[1]
        action = parse_qs(target.split("?", 1)[1])["action"][0]
        return {"err": 0, "dat": routes[action]}

    session, connector = cloud_transport
    connector.payload = respond
    api = DessMonitorAPI(
        "test-user", "test-password", session=session, api_profile="shinemonitor_solar"
    )
    api.token, api.secret = "test-token", "test-secret"
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    try:
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        hass.data[DOMAIN] = {"entry": coordinator}
        added = MagicMock()
        await async_setup_entry(hass, MagicMock(entry_id="entry"), added)
        entities = added.call_args.args[0]
        today = [e for e in entities if e.name.endswith(" Energy Today")]
        total = [e for e in entities if e.name.endswith(" Energy Total")]
        assert len(today) == 1, [(e.unique_id, e.native_value) for e in today]
        assert len(total) == 1, [(e.unique_id, e.native_value) for e in total]
    finally:
        await coordinator.async_shutdown()
