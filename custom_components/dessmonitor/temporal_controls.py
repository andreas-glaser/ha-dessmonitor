"""Cloud-backed wall-clock controls for verified devcode 6544 field IDs."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DessMonitorDataUpdateCoordinator
from .const import DOMAIN
from .control_values import cloud_control_snapshot, control_value, find_control_value
from .device_support.device_registry import map_control_field
from .entity_loader import async_setup_dynamic_entities
from .temporal_fields import temporal_control_kind
from .utils import control_entity_suffix, create_device_info

_MIGRATION_OPTION = "temporal_number_migrated"


async def async_setup_temporal_platform(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    kind: str,
    entity_type: type[DessMonitorTemporalControl],
) -> None:
    """Reuse bounded cloud discovery and retire corresponding numeric entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    async def build() -> list[DessMonitorTemporalControl]:
        entities = await async_build_temporal_entities(
            coordinator, known, kind, entity_type
        )
        disable_replaced_numbers(hass, entry, entities)
        return entities

    await async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        async_add_entities,
        build,
        task_name=f"dessmonitor_{kind}_discovery",
        defer_initial=True,
    )


async def async_build_temporal_entities(
    coordinator: DessMonitorDataUpdateCoordinator,
    known: set[str],
    kind: str,
    entity_type: type[DessMonitorTemporalControl],
) -> list[DessMonitorTemporalControl]:
    """Create controls only when the API advertises the matching value field."""
    entities: list[DessMonitorTemporalControl] = []
    for serial, payload in (coordinator.data or {}).items():
        device = payload.get("device", {})
        collector = payload.get("collector", {})
        devcode = device.get("devcode")
        address = device.get("devaddr")
        pn = collector.get("pn")
        if str(devcode) != "6544" or not pn or address is None:
            continue
        controls, values = await coordinator.async_get_controls_with_values(
            pn, devcode, address, serial
        )
        for name, config in controls.items():
            field_id = config.get("id")
            if (
                config.get("type") != "value"
                or temporal_control_kind(devcode, field_id) != kind
            ):
                continue
            key = f"{serial}:{field_id}"
            if key in known:
                continue
            entities.append(
                entity_type(
                    coordinator,
                    serial,
                    device,
                    collector,
                    name,
                    field_id,
                    values.get(field_id),
                )
            )
            known.add(key)
    return entities


def disable_replaced_numbers(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entities: list[DessMonitorTemporalControl],
) -> None:
    """Retire each old number once, preserving subsequent user overrides."""
    registry = er.async_get(hass)
    for entity in entities:
        for unique_id in entity.legacy_number_unique_ids:
            entity_id = registry.async_get_entity_id("number", DOMAIN, unique_id)
            if entity_id is None:
                continue
            old = registry.async_get(entity_id)
            if old is None or old.config_entry_id != entry.entry_id:
                continue
            options = dict(old.options.get(DOMAIN, {}))
            if options.get(_MIGRATION_OPTION) is True:
                continue
            if old.disabled_by is None:
                registry.async_update_entity(
                    entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                )
            # Persist the decision per old record, including user-disabled ones.
            # A later user re-enable must survive discovery and registry reload.
            # Both updates are synchronous callbacks and cannot interleave.
            options[_MIGRATION_OPTION] = True
            registry.async_update_entity_options(entity_id, DOMAIN, options)


class DessMonitorTemporalControl(CoordinatorEntity[DessMonitorDataUpdateCoordinator]):
    """Share cloud recovery and writes without inventing a timezone or default."""

    _attr_native_value: Any
    _attr_entity_category = EntityCategory.CONFIG
    value_format: str

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        serial: str,
        device: dict[str, Any],
        collector: dict[str, Any],
        api_name: str,
        field_id: str,
        initial_value: Any,
    ) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._api_name = api_name
        self._field_id = field_id
        friendly = map_control_field(device["devcode"], api_name)
        self._attr_name = f"{device.get('alias', 'DessMonitor')} {friendly.strip()}"
        self._attr_unique_id = f"{serial}_{field_id}"
        # Upgrades can carry either the raw vendor-name ID (before #57) or
        # the normalized/mapped ID. Retire both without renaming either record.
        self.legacy_number_unique_ids = tuple(
            dict.fromkeys(
                f"{serial}_{control_entity_suffix(candidate)}"
                for candidate in (api_name, friendly)
            )
        )
        self._attr_device_info = create_device_info(serial, device, collector)
        self._last_cloud_sample = cloud_control_snapshot(coordinator, serial)[0]
        self._last_raw_value = control_value(initial_value)
        self._attr_native_value = self._parse_value(self._last_raw_value)

    def _parse_value(self, raw: str | None) -> Any:
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        status = "last_known"
        if self._attr_native_value is None:
            status = "unsupported_format" if self._last_raw_value else "not_loaded"
        return {
            "control_transport": "cloud",
            "value_status": status,
            "value_format": self.value_format,
            "time_basis": "inverter_wall_clock",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        stamp, points = cloud_control_snapshot(self.coordinator, self._serial)
        raw = control_value(
            self.coordinator.ctrl_value_cache.get(self._serial, {}).get(self._field_id)
        )
        if stamp != self._last_cloud_sample:
            self._last_cloud_sample = stamp
            cloud_raw = find_control_value(points, self._api_name)
            if self._parse_value(cloud_raw) is not None:
                raw = cloud_raw
        if raw is not None:
            self._last_raw_value = raw
            value = self._parse_value(raw)
            if value is not None:
                self._attr_native_value = value
        super()._handle_coordinator_update()

    async def _async_write_value(self, raw: str) -> None:
        """Publish a new value only after the single cloud write succeeds."""
        value = self._parse_value(raw)
        if value is None:
            raise ValueError(f"Expected {self.value_format}")
        payload = (self.coordinator.data or {}).get(self._serial, {})
        device = payload.get("device", {})
        collector = payload.get("collector", {})
        if not collector.get("pn") or device.get("devaddr") is None:
            raise ValueError("Device route is unavailable")
        if temporal_control_kind(device.get("devcode"), self._field_id) is None:
            raise ValueError("Unsupported temporal control route")
        await self.coordinator.api.set_device_control_value(
            pn=collector["pn"],
            devcode=device["devcode"],
            devaddr=device["devaddr"],
            sn=self._serial,
            param_id=self._field_id,
            value=raw,
        )
        self._last_cloud_sample = cloud_control_snapshot(
            self.coordinator, self._serial
        )[0]
        self.coordinator.ctrl_value_cache.setdefault(self._serial, {})[
            self._field_id
        ] = raw
        self._last_raw_value = raw
        self._attr_native_value = value
        self.async_write_ha_state()
