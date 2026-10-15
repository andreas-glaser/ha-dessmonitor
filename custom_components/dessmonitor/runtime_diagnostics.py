"""Read-only diagnostics for source selection and HA entity publication.

Only allowlisted runtime fields are exported. Account data, raw identifiers,
network addresses, exception messages and protocol payloads are excluded.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_DEVICE_ADDRESS,
    CONF_LOCAL_MODE,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from .local.hybrid import DessMonitorHybridCoordinator, merge_cloud_and_local

_SOURCES = {"Cloud", "Local", "Cached Cloud", "Unknown", "unknown", "unavailable"}
_CODE_FILES = (
    "manifest.json",
    "__init__.py",
    "const.py",
    "sensor.py",
    "select.py",
    "number.py",
    "control_values.py",
    "device_support/devcode_6544.py",
    "diagnostics.py",
    "local/hybrid.py",
    "local/coordinator.py",
    "local/drivers.py",
    "local/smg_protocol4.py",
    "local/smg.py",
    "runtime_diagnostics.py",
)


def _ref(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return "sha256:" + hashlib.sha256(str(value).encode()).hexdigest()[:12]


def _source(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and value in _SOURCES else "unexpected"


def _timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return None


def _number(value: Any) -> int | None:
    if type(value) is int:
        return value
    if (
        isinstance(value, str)
        and value.isascii()
        and value.isdigit()
        and len(value) < 10
    ):
        return int(value)
    return None


def _devices(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    result: list[dict[str, Any]] = []
    for serial, payload in data.items():
        if not isinstance(payload, dict):
            result.append(
                {"device_ref": _ref(serial), "payload_type": type(payload).__name__}
            )
            continue
        device = payload.get("device", {})
        points = payload.get("data", [])
        address = device.get("devaddr")
        verified = device.get("local_address_verified")
        result.append(
            {
                "device_ref": _ref(serial),
                "collector_ref": _ref(payload.get("collector", {}).get("pn")),
                "device_code": _number(device.get("devcode")),
                "address": _number(address),
                "address_type": type(address).__name__,
                # Missing or malformed metadata is not evidence of verification.
                "address_verified": verified if isinstance(verified, bool) else None,
                "point_count": len(points),
                "data_sources": [
                    _source(p.get("val"))
                    for p in points
                    if p.get("title") == "Data Source"
                ],
                "timestamps": [
                    _timestamp(p.get("val"))
                    for p in points
                    if p.get("title") == "Timestamp"
                ],
            }
        )
    return result


def _code_hashes() -> dict[str, str | None]:
    root = Path(__file__).parent
    result: dict[str, str | None] = {}
    for name in _CODE_FILES:
        try:
            result[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        except OSError:
            result[name] = None
    return result


def _source_entities(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, Any]]:
    registry = er.async_get(hass)
    component = hass.data.get("entity_components", {}).get("sensor") or hass.data.get(
        "sensor"
    )
    coordinators = hass.data.get(DOMAIN, {})
    result: list[dict[str, Any]] = []
    for registered in registry.entities.values():
        if (
            registered.platform != DOMAIN
            or registered.domain != "sensor"
            or not registered.unique_id.endswith("_data_source")
        ):
            continue
        owner = coordinators.get(registered.config_entry_id)
        serial = registered.unique_id.removesuffix("_data_source")
        state = hass.states.get(registered.entity_id)
        get_entity = getattr(component, "get_entity", None)
        entity = get_entity(registered.entity_id) if callable(get_entity) else None
        native = calculated = read_error = None
        getter_owner = getter_type = None
        if entity is not None:
            for owner_class in type(entity).__mro__:
                if "native_value" in owner_class.__dict__:
                    getter_owner = owner_class.__name__
                    getter_type = type(owner_class.__dict__["native_value"]).__name__
                    break
            try:
                native = _source(entity.native_value)
                calculated = _source(entity.state)
            except Exception as err:  # Diagnostics must survive the broken entity.
                read_error = type(err).__name__
        listeners = getattr(owner, "_listeners", {})
        listener_registered = None
        if entity is not None and isinstance(listeners, dict):
            listener_registered = any(
                getattr(callback, "__self__", None) is entity
                for callback, _context in listeners.values()
            )
        payload = (getattr(owner, "data", None) or {}).get(serial, {})
        result.append(
            {
                "entity_ref": _ref(registered.entity_id),
                "device_ref": _ref(serial),
                "owner_entry_ref": _ref(registered.config_entry_id),
                "belongs_to_requested_entry": registered.config_entry_id
                == entry.entry_id,
                "disabled_by": (
                    str(registered.disabled_by) if registered.disabled_by else None
                ),
                "ha_state": _source(state.state) if state else None,
                "ha_last_updated": _timestamp(state.last_updated) if state else None,
                "ha_last_reported": (
                    _timestamp(getattr(state, "last_reported", None)) if state else None
                ),
                "entity_object_present": entity is not None,
                "entity_class": type(entity).__name__ if entity is not None else None,
                "instance_device_ref": _ref(getattr(entity, "_device_sn", None)),
                "platform_state": getattr(
                    getattr(entity, "_platform_state", None), "name", None
                ),
                "native_value_owner": getter_owner,
                "native_value_descriptor": getter_type,
                "enum_options": (
                    [_source(option) for option in entity.options]
                    if entity is not None
                    and isinstance(getattr(entity, "options", None), list)
                    else None
                ),
                "bound_to_owner_coordinator": (
                    (getattr(entity, "coordinator", None) is owner)
                    if entity is not None
                    else None
                ),
                "listener_registered": listener_registered,
                "native_value": native,
                "calculated_state": calculated,
                "entity_read_error": read_error,
                "coordinator_sources": [
                    _source(p.get("val"))
                    for p in payload.get("data", [])
                    if p.get("title") == "Data Source"
                ],
            }
        )
    return result


async def async_runtime_report(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Compare snapshots, entity binding and HA state without requesting refreshes."""
    hashes = await hass.async_add_executor_job(_code_hashes)
    integration = await async_get_integration(hass, DOMAIN)
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    report: dict[str, Any] = {
        "schema_version": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "home_assistant_version": HA_VERSION,
        "integration_version": integration.version,
        "code_sha256": hashes,
        "requested_entry_ref": _ref(entry.entry_id),
        "entry_state": str(entry.state.value),
        "cloud_polling_disabled": entry.pref_disable_polling,
    }
    if coordinator is None:
        report["error"] = "entry_not_loaded"
        return report
    settings = {**entry.data, **entry.options}
    pending_push = getattr(coordinator, "_local_push_handle", None)
    report["configured"] = {
        "connection_type": (
            settings.get(CONF_CONNECTION_TYPE)
            if settings.get(CONF_CONNECTION_TYPE) in ("cloud", "local")
            else "default_or_unknown"
        ),
        "local_mode": (
            settings.get(CONF_LOCAL_MODE)
            if settings.get(CONF_LOCAL_MODE) in ("disabled", "prefer_local")
            else "default_or_unknown"
        ),
        "cloud_interval": _number(settings.get(CONF_UPDATE_INTERVAL)),
        "local_interval": _number(settings.get(CONF_LOCAL_POLL_INTERVAL)),
        "inverter_address": _number(settings.get(CONF_LOCAL_DEVICE_ADDRESS)),
    }
    report["coordinator"] = {
        "class": type(coordinator).__name__,
        "last_update_success": coordinator.last_update_success,
        "last_exception_type": (
            type(coordinator.last_exception).__name__
            if coordinator.last_exception
            else None
        ),
        "cloud_revision": getattr(coordinator, "cloud_revision", None),
        "initial_refresh_completed": getattr(
            coordinator, "_initial_refresh_completed", None
        ),
        "cloud_stale": getattr(coordinator, "_cloud_stale", None),
        "hybrid_shutdown": getattr(coordinator, "_shutdown", None),
        "shutdown_requested": getattr(coordinator, "_shutdown_requested", None),
        "local_push_pending": pending_push is not None,
        "local_push_cancelled": pending_push.cancelled() if pending_push else None,
        "listener_count": len(getattr(coordinator, "_listeners", {})),
    }
    report["published_devices"] = _devices(coordinator.data)
    report["cached_cloud_devices"] = _devices(
        getattr(coordinator, "_cached_cloud_data", {})
    )
    routes = getattr(coordinator, "locals", ())
    report["local_routes"] = [
        {
            "connected": route.connected,
            "last_update_success": route.last_update_success,
            "last_exception_type": (
                type(route.last_exception).__name__ if route.last_exception else None
            ),
            "tunnel_code": route.device_code,
            "listener_count": len(getattr(route, "_listeners", {})),
            "hybrid_listener_registered": any(
                getattr(callback, "__self__", None) is coordinator
                for callback, _context in getattr(route, "_listeners", {}).values()
            ),
            "devices": _devices(route.data),
        }
        for route in routes
    ]
    if isinstance(coordinator, DessMonitorHybridCoordinator):
        local_data = coordinator._current_local_data()
        expected = merge_cloud_and_local(
            coordinator._cached_cloud_data,
            local_data,
            local_available=bool(local_data),
            cloud_source="Cached Cloud" if coordinator._cloud_stale else "Cloud",
        )
        report["recomputed_hybrid_devices"] = _devices(expected)
    report["data_source_entities"] = _source_entities(hass, entry)
    return report
