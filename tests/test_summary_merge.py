"""Plant-summary merge: one reading must not publish two entities.

``energyToday`` and ``Energy Today`` are separate ``SENSOR_TYPES`` keys that
both appear as "Energy Today". A devcode that maps the device's own counter
onto the second one, while the plant summary supplies the first, used to
publish both: two entities with one name, and on an account where the vendor
leaves the summary field unset the duplicate reads 0 kWh (#58).

The merge compared raw and devcode-mapped titles, so it only caught a profile
that mapped the summary title itself. Devcodes 2452 and 518 each carry that
pair as a per-profile workaround, added after the duplicates were reported
against them; the devcodes that do not were still exposed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import pytest

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
from custom_components.dessmonitor.api import DessMonitorAPI
from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.sensor import async_setup_entry

# Each case is a devcode that maps its own energy counters onto the canonical
# keys, with the titles that collector reports.
CASES = [
    pytest.param(
        4743,
        "PV power generation today",
        "Total photovoltaic power generation",
        id="devcode_4743",
    ),
    pytest.param(
        6515,
        "Daily PV energy generation",
        "Total PV energy generation",
        id="devcode_6515",
    ),
    pytest.param(2449, "Today generation", "Total generation", id="devcode_2449"),
    pytest.param(684, "today energy", "total energy", id="devcode_684"),
]


def _routes(devcode: int, today: str, total: str) -> dict[str, Any]:
    return {
        "queryPlants": {"plant": [{"pid": 1}]},
        "webQueryCollectorsEs": {
            "collector": [{"pn": "REDACTED-PN", "pid": 1}],
            "total": 1,
        },
        "queryCollectorDevices": {
            "dev": [{"sn": "REDACTED-SN", "devcode": devcode, "devaddr": 1}]
        },
        "queryDeviceLastData": [
            {"title": today, "val": "12.0", "unit": "kWh"},
            {"title": total, "val": "4174.6", "unit": "kWh"},
        ],
        # The vendor leaves these unset on the reporter's account.
        "webQueryDeviceEs": {
            "device": [
                {"sn": "REDACTED-SN", "outpower": 0, "energyToday": 0, "energyTotal": 0}
            ]
        },
    }


@pytest.mark.parametrize(("devcode", "today", "total"), CASES)
async def test_summary_does_not_duplicate_a_mapped_energy_counter(
    hass, cloud_transport, devcode: int, today: str, total: str
) -> None:
    routes = _routes(devcode, today, total)

    def respond(request: bytes) -> dict[str, Any]:
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

        today_entities = [e for e in entities if e.name.endswith(" Energy Today")]
        total_entities = [e for e in entities if e.name.endswith(" Energy Total")]
        assert len(today_entities) == 1, [
            (e.unique_id, e.native_value) for e in today_entities
        ]
        assert len(total_entities) == 1, [
            (e.unique_id, e.native_value) for e in total_entities
        ]
        # The device's own reading wins; the unset summary field is not shown.
        assert today_entities[0].native_value == 12.0
        assert total_entities[0].native_value == 4174.6
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(("devcode", "today", "total"), CASES[:1])
async def test_the_download_records_what_the_merge_dropped(
    hass, cloud_transport, devcode: int, today: str, total: str
) -> None:
    """The cloud's own figure for a sensor the device feeds has to be visible.

    An owner comparing the vendor app's daily energy against Home Assistant's
    is comparing the dropped summary field against the device's own counter,
    and the download used to record only the one that won (#58).
    """
    routes = _routes(devcode, today, total)
    routes["webQueryDeviceEs"] = {
        "device": [
            {
                "sn": "REDACTED-SN",
                "outpower": 0.9,
                "energyToday": 1.0,
                "energyTotal": 4174.6,
            }
        ]
    }

    def respond(request: bytes) -> dict[str, Any]:
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

        dropped = coordinator.summary_points_not_merged["REDACTED-SN"]

        # The device's own counters already reach both entities, so the
        # cloud's two energy figures are recorded rather than published.
        assert dropped == [
            {"title": "energyToday", "value": "1.0", "unit": "kWh"},
            {"title": "energyTotal", "value": "4174.6", "unit": "kWh"},
        ]
        # "outpower" has no counterpart on this device, so it is merged and is
        # not a dropped point.
        titles = {point["title"] for point in coordinator.data["REDACTED-SN"]["data"]}
        assert "outpower" in titles
    finally:
        await coordinator.async_shutdown()


async def test_a_device_the_account_stops_listing_leaves_no_record(
    hass, cloud_transport
) -> None:
    """The record is rebuilt per fetch, so removed hardware disappears from it."""
    routes = _routes(4743, "PV power generation today", "Total photovoltaic power generation")

    def respond(request: bytes) -> dict[str, Any]:
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
        assert "REDACTED-SN" in coordinator.summary_points_not_merged

        routes["queryCollectorDevices"] = {
            "dev": [{"sn": "OTHER-SN", "devcode": 4743, "devaddr": 1}]
        }
        routes["webQueryDeviceEs"] = {
            "device": [{"sn": "OTHER-SN", "energyToday": 2.0}]
        }
        await coordinator.async_refresh()

        assert "REDACTED-SN" not in coordinator.summary_points_not_merged
    finally:
        await coordinator.async_shutdown()
