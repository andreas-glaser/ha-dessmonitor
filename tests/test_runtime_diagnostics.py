"""Runtime reports distinguish source selection from entity publication safely."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor.const import DOMAIN
from custom_components.dessmonitor.diagnostics import async_get_config_entry_diagnostics
from custom_components.dessmonitor.local.hybrid import DessMonitorHybridCoordinator


def _payload(serial, source):
    return {
        serial: {
            "collector": {"pn": "PRIVATE-PN", "ip": "192.168.10.58"},
            "device": {"devcode": 6544, "devaddr": 1, "alias": "PRIVATE-ALIAS"},
            "data": [
                {"title": "Data Source", "val": source},
                {"title": "Timestamp", "val": "2026-10-15T12:00:00+00:00"},
                {"title": "irrelevant", "val": "PRIVATE-PAYLOAD"},
            ],
        }
    }


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "PRIVATE-USER",
            "password": "PRIVATE-PASSWORD",
            "connection_type": "cloud",
        },
        options={"local_mode": "prefer_local", "local_listen_ip": "192.168.10.60"},
    )
    entry.add_to_hass(hass)
    return entry


async def _report(hass, entry):
    with (
        patch(
            "custom_components.dessmonitor.runtime_diagnostics._code_hashes",
            return_value={"sensor.py": "hash"},
        ),
        patch(
            "custom_components.dessmonitor.runtime_diagnostics.async_get_integration",
            AsyncMock(return_value=SimpleNamespace(version="2.5.0+protocol4.3")),
        ),
    ):
        return await async_get_config_entry_diagnostics(hass, entry)


async def test_report_distinguishes_native_value_and_ha_state_without_requests(hass):
    entry = _entry(hass)
    coordinator = SimpleNamespace(
        data=_payload("PRIVATE-SN", "Local"),
        _cached_cloud_data=_payload("PRIVATE-SN", "Cloud"),
        last_update_success=True,
        last_exception=None,
        cloud_revision=1,
        _listeners={},
        api=AsyncMock(),
        async_request_refresh=AsyncMock(),
    )
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    registered = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        "PRIVATE-SN_data_source",
        config_entry=entry,
        suggested_object_id="private_data_source",
    )
    hass.states.async_set(registered.entity_id, "Cloud")

    class SourceEntity:
        native_value = "Local"
        state = "Local"
        options = ["Cloud", "Local", "Cached Cloud"]

        def update(self):
            pass

    entity = SourceEntity()
    entity.coordinator = coordinator
    coordinator._listeners[1] = (entity.update, None)
    hass.data["entity_components"] = {
        "sensor": SimpleNamespace(get_entity=lambda _id: entity)
    }
    report = await _report(hass, entry)
    (source,) = report["data_source_entities"]
    assert source["ha_state"] == "Cloud"
    assert source["native_value"] == source["calculated_state"] == "Local"
    assert source["coordinator_sources"] == ["Local"]
    assert source["bound_to_owner_coordinator"] is True
    assert source["listener_registered"] is True
    assert source["enum_options"] == ["Cloud", "Local", "Cached Cloud"]
    assert report["published_devices"][0]["data_sources"] == ["Local"]
    assert report["configured"]["local_mode"] == "prefer_local"
    coordinator.async_request_refresh.assert_not_awaited()
    assert not coordinator.api.mock_calls
    encoded = json.dumps(report)
    for private in (
        "PRIVATE-SN",
        "PRIVATE-PN",
        "PRIVATE-USER",
        "PRIVATE-PASSWORD",
        "PRIVATE-ALIAS",
        "PRIVATE-PAYLOAD",
        "192.168.10.58",
        "192.168.10.60",
        registered.entity_id,
        entry.entry_id,
    ):
        assert private not in encoded


async def test_report_identifies_unpublished_local_snapshot(hass):
    entry = _entry(hass)
    api = AsyncMock(token="PRIVATE-TOKEN", secret="PRIVATE-SECRET")
    coordinator = DessMonitorHybridCoordinator(
        hass,
        api,
        300,
        {"local_listen_ip": "192.168.10.60", "local_collector_ip": "192.168.10.58"},
        entry.entry_id,
    )
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    coordinator.data = _payload("CLOUD-SERIAL", "Cloud")
    coordinator._cached_cloud_data = coordinator.data
    coordinator.local.data = _payload("LOCAL-SERIAL", "Local")
    try:
        report = await _report(hass, entry)
        assert report["published_devices"][0]["data_sources"] == ["Cloud"]
        assert report["recomputed_hybrid_devices"][0]["data_sources"] == ["Local"]
        assert report["coordinator"]["initial_refresh_completed"] is False
        assert report["coordinator"]["hybrid_shutdown"] is False
        assert report["local_routes"][0]["hybrid_listener_registered"] is True
        assert report["local_routes"][0]["devices"][0]["data_sources"] == ["Local"]
        assert not api.mock_calls
    finally:
        await coordinator.async_shutdown()


async def test_disabled_source_with_no_entity_object_is_reported(hass):
    entry = _entry(hass)
    coordinator = SimpleNamespace(
        data={}, last_update_success=True, last_exception=None
    )
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        "PRIVATE-SN_data_source",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    report = await _report(hass, entry)
    (source,) = report["data_source_entities"]
    assert source["disabled_by"] is not None
    assert source["entity_object_present"] is False
    assert source["ha_state"] is None


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({}, None),
        ({"local_address_verified": True}, True),
        ({"local_address_verified": False}, False),
        ({"local_address_verified": None}, None),
        ({"local_address_verified": 1}, None),
        ({"local_address_verified": "PRIVATE-FLAG"}, None),
    ],
)
async def test_address_verification_requires_explicit_boolean(hass, metadata, expected):
    """An absent flag in cloud data must not imply a verified local address."""
    entry = _entry(hass)
    data = _payload("PRIVATE-SN", "Cloud")
    data["PRIVATE-SN"]["device"].update(metadata)
    hass.data[DOMAIN] = {
        entry.entry_id: SimpleNamespace(
            data=data, last_update_success=True, last_exception=None
        )
    }
    report = await _report(hass, entry)
    assert report["published_devices"][0]["address_verified"] is expected
    assert "PRIVATE-FLAG" not in json.dumps(report)


async def test_unloaded_entry_report_does_not_fail(hass):
    entry = _entry(hass)
    report = await _report(hass, entry)
    assert report["error"] == "entry_not_loaded"
    assert "PRIVATE-PASSWORD" not in json.dumps(report)
