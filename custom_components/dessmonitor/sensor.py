"""Platform for DessMonitor sensor integration."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import DessMonitorDataUpdateCoordinator
from .const import DOMAIN, SENSOR_TYPES, UNITS
from .device_support import (
    apply_devcode_transformations,
    get_all_charger_priorities,
    get_all_operating_modes,
    get_all_output_priorities,
    is_devcode_supported,
)
from .sensor_titles import (
    normalize_sensor_title,
    resolve_sensor_key,
    sensor_display_name,
)
from .utils import create_device_info

_LOGGER = logging.getLogger(__name__)

ENUM_SENSOR_TITLES = {
    "Data Source",
    "Operating mode",
    "Output priority",
    "Charger Source Priority",
    "work state",
    "charger work enable",
}

# Readings whose value is free-form text rather than one of a fixed set of
# states. Coercing these to a float would publish nothing at all, and giving
# them the enum device class would reject any word not in an option list.
#
# A key that belongs here and is missing reads unknown for ever, which is how
# the four per-subsystem status sensors below shipped: they were added to
# SENSOR_TYPES as text sensors and never declared here, so every value the
# vendor sent ("Battery Discharge", "Load On (Normal)") was offered to float()
# and discarded (#81). ``test_sensor_value_types`` fails on the next one.
TEXT_SENSOR_TITLES = {
    "Inverter Status",
    # Devcode 6489 names the charger's stage ("Stop charging") rather than
    # measuring it, and no report carries the vendor's full set of strings.
    "Charge Mode",
    # The per-subsystem status texts a Voltronic-family collector sends
    # alongside the operating mode.
    "Battery Status",
    "PV Status",
    "Grid Status",
    "Load Status",
    # A version is a label, not a quantity. Read as a number it either
    # vanished - "V1.08", "1.08.3" and "0080-A" cannot survive float(), so
    # the sensor read unknown with nothing in the log to say why - or lost a
    # digit, publishing "1.080" as 1.08. This is the one key in SENSOR_TYPES
    # that measures nothing and was still read as a number (#84).
    "Software version",
    # Devcode 567 answers its own switch with "Stop state" or "On-grid
    # operation" and its anti-PID module with "Not running". Both are the
    # vendor's words and neither is a set anything here knows, so they are
    # text rather than enums (#89).
    "Inverter Switch Status",
    "PID Status",
    # Devcode 659 answers whether it restarts itself with "Automatically
    # Boot". Another word, and the vendor documents no set of them (#92).
    "Automatic Startup",
}


# How many values one enum sensor may collect beyond the registered ones.
# A vendor's state set is small; a number misread as an enumeration is not.
_MAX_ENUM_OPTIONS = 64

# The synthetic diagnostic sensor that says when a device last reported
# something new, and the reading it watches for movement.
LAST_READING_KEY = "Last Reading Received"
_TIMESTAMP_TITLE_KEY = normalize_sensor_title("Timestamp")


def _name_marker(device_sn: str, sensor_type: str) -> str:
    """Return the per-device marker two sensor types sharing a name collide on.

    Separate keys can carry one display name on purpose, each a vendor's own
    spelling: ``SOC`` beside ``State of Charge``, ``Batt Current`` beside
    ``Battery Current``, ``energyToday`` beside ``Energy Today``. A collector
    that reports one of each resolves them to two keys, so the key-level check
    below lets both through and the device gets two entities with one name,
    the second of them reading whatever the vendor left in the field it came
    from (#58). The marker is kept in the same set and cannot collide with a
    sensor key, which has no NUL in it.
    """
    return f"name\x00{device_sn}\x00{sensor_display_name(sensor_type)}"


def _normalize_devcode(value: Any) -> int | None:
    """Normalize raw devcode payloads to integers when possible."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _build_source_title_set(*titles: str | None) -> set[str]:
    """Create the set of raw titles that should map back to a canonical sensor."""
    resolved: set[str] = set()
    for title in titles:
        if not isinstance(title, str):
            continue

        stripped = title.strip()
        if stripped:
            resolved.add(stripped)
    return resolved


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DessMonitor sensors based on a config entry."""
    _LOGGER.debug(
        "Setting up DessMonitor sensors for config entry: %s", config_entry.entry_id
    )
    coordinator: DessMonitorDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    known_sensors: set[str] = set()

    def _add_new_entities() -> None:
        entities = _build_sensor_entities(coordinator, known_sensors)
        if entities:
            _LOGGER.info("Adding %d DessMonitor sensor entities", len(entities))
            # Coordinator data is already current. update_before_add would make
            # every dynamic batch request another full cloud refresh.
            async_add_entities(entities)

    _add_new_entities()
    config_entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


def _carries_a_timestamp(device_data: Any) -> bool:
    """Return whether this payload carries the vendor's own timestamp.

    The freshness sensor watches that field for movement, so a device whose
    payload has none gets no sensor rather than one that could only ever
    report when the entry was set up.
    """
    return isinstance(device_data, list) and any(
        isinstance(point, dict) and _is_timestamp_title(point.get("title"))
        for point in device_data
    )


def _is_timestamp_title(title: Any) -> bool:
    """Return whether a reading's title is the vendor's own timestamp."""
    return (
        isinstance(title, str) and normalize_sensor_title(title) == _TIMESTAMP_TITLE_KEY
    )


def _build_sensor_entities(
    coordinator: DessMonitorDataUpdateCoordinator, known_sensors: set[str]
) -> list[DessMonitorSensor]:
    """Build newly discovered sensor entities from coordinator data."""
    if not coordinator.data:
        return []
    if not isinstance(coordinator.data, dict):
        _LOGGER.warning("Unexpected coordinator data type %s", type(coordinator.data))
        return []

    entities: list[DessMonitorSensor] = []
    coordinator_data = cast(dict[str, dict[str, Any]], coordinator.data)

    for device_sn, raw_device_info in coordinator_data.items():
        device_info = cast(dict[str, Any], raw_device_info)
        device_data = device_info.get("data", [])
        device_meta = device_info.get("device", {})
        collector_meta = device_info.get("collector", {})

        supported_sensors = 0
        duplicate_sensors = 0

        freshness_key = f"{device_sn}_{LAST_READING_KEY}"
        if freshness_key not in known_sensors and _carries_a_timestamp(device_data):
            known_sensors.add(freshness_key)
            known_sensors.add(_name_marker(device_sn, LAST_READING_KEY))
            entities.append(
                DessMonitorLastReadingSensor(
                    coordinator=coordinator,
                    device_sn=device_sn,
                    device_meta=device_meta,
                    collector_meta=collector_meta,
                )
            )

        devcode = _normalize_devcode(device_meta.get("devcode"))
        devcode_supported = devcode is not None and is_devcode_supported(devcode)

        for data_point in device_data:
            original_title = data_point.get("title")
            transformed_title = original_title

            if devcode_supported and devcode is not None:
                transformed_title = apply_devcode_transformations(
                    devcode, data_point.copy()
                ).get("title", transformed_title)

            sensor_type = resolve_sensor_key(transformed_title, original_title)
            if not sensor_type:
                continue

            sensor_key = f"{device_sn}_{sensor_type}"
            if sensor_key in known_sensors:
                duplicate_sensors += 1
                continue

            name_marker = _name_marker(device_sn, sensor_type)
            if name_marker in known_sensors:
                duplicate_sensors += 1
                _LOGGER.debug(
                    "Skipping %s for device %s: another reading already "
                    "publishes that name",
                    sensor_type,
                    device_sn,
                )
                continue

            known_sensors.add(sensor_key)
            known_sensors.add(name_marker)
            source_titles = _build_source_title_set(
                sensor_type, original_title, transformed_title
            )
            entities.append(
                DessMonitorSensor(
                    coordinator=coordinator,
                    device_sn=device_sn,
                    device_meta=device_meta,
                    collector_meta=collector_meta,
                    sensor_type=sensor_type,
                    data_point=data_point,
                    source_titles=source_titles,
                )
            )
            supported_sensors += 1
            _LOGGER.debug(
                "Created sensor: %s for device %s (aliases: %s)",
                sensor_type,
                device_sn,
                ", ".join(sorted(source_titles)),
            )

        if supported_sensors:
            _LOGGER.debug(
                "Device %s: created %d sensors, skipped %d duplicates",
                device_sn,
                supported_sensors,
                duplicate_sensors,
            )

    return entities


class DessMonitorSensor(CoordinatorEntity, SensorEntity):
    """Representation of a DessMonitor sensor."""

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
        sensor_type: str,
        data_point: dict[str, Any],
        source_titles: set[str] | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._device_sn = device_sn
        self._device_meta = device_meta
        self._collector_meta = collector_meta
        self._sensor_type = sensor_type
        self._source_titles = source_titles or {sensor_type}
        # Compared in their normalized form. The cloud and a local driver can
        # spell one reading differently: devcode 2452 reports "Grid frequency"
        # while the PI18 profile emits "Grid Frequency", and the hybrid overlay
        # replaces the cloud point with the local one, title included. Matching
        # the raw spelling left the entity unknown for as long as local
        # telemetry flowed, which is what #53 saw as holes in its history.
        self._source_title_keys = frozenset(
            normalize_sensor_title(title)
            for title in self._source_titles
            if isinstance(title, str)
        )

        sensor_config: dict[str, Any] = cast(
            dict[str, Any], SENSOR_TYPES.get(sensor_type, {})
        )

        self._initialize_identity(sensor_config)
        self._apply_unit_metadata(sensor_config.get("unit", ""))
        self._apply_sensor_traits(sensor_config, data_point)

        self._attr_device_info = create_device_info(
            device_sn, device_meta, collector_meta
        )

        _LOGGER.debug(
            "Initialized sensor: name='%s', unique_id='%s', device='%s', type='%s'",
            self._attr_name,
            self._attr_unique_id,
            device_sn,
            sensor_type,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return cast(DeviceInfo, self._attr_device_info)

    def _initialize_identity(self, sensor_config: dict[str, Any]) -> None:
        """Initialise name and unique ID for the entity."""
        device_alias = self._device_meta.get("alias", "DessMonitor")
        sensor_name = sensor_config.get("name", self._sensor_type)
        self._attr_name = f"{device_alias} {sensor_name}"

        unique_suffix = self._build_unique_suffix(self._sensor_type)
        self._attr_unique_id = f"{self._device_sn}_{unique_suffix}"

    @staticmethod
    def _build_unique_suffix(sensor_type: str) -> str:
        """Create a consistent suffix for unique_id generation."""
        return sensor_type.lower().replace(" ", "_").replace("-", "_")

    def _apply_unit_metadata(self, unit: str) -> None:
        """Configure unit/device class metadata with sensible defaults."""
        native_unit, device_class, precision = self._unit_metadata_from_unit(unit)
        self._attr_native_unit_of_measurement = native_unit

        if device_class is not None:
            self._attr_device_class = device_class

        if precision is not None:
            self._attr_suggested_display_precision = precision

    @staticmethod
    def _unit_metadata_from_unit(
        unit: str,
    ) -> tuple[
        str
        | UnitOfPower
        | UnitOfEnergy
        | UnitOfElectricPotential
        | UnitOfElectricCurrent
        | UnitOfFrequency
        | UnitOfTemperature
        | None,
        SensorDeviceClass | None,
        int | None,
    ]:
        """Return (native_unit, device_class, precision) for a given unit string."""
        if not unit.strip():
            # None, not "": Home Assistant tests for the presence of the
            # unit_of_measurement attribute rather than for a value, so an
            # empty string made every text and enum sensor we publish look
            # like a continuous measurement. The logbook skips those, and its
            # historical query filters them out, so Data Source and Operating
            # mode had no Activity at all and drew an empty numeric chart
            # instead of a state timeline (#53). Power Factor is the only
            # unitless reading that really is continuous, and it says so with
            # its state class.
            return None, None, None
        if unit == UNITS["POWER"]:
            return UnitOfPower.WATT, SensorDeviceClass.POWER, None
        if unit == UNITS["POWER_KW"]:
            return UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, None
        if unit == UNITS["ENERGY"]:
            return UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, None
        if unit == UNITS["VOLTAGE"]:
            return UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, 1
        if unit == UNITS["CURRENT"]:
            return UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, 1
        if unit in {UNITS["FREQUENCY"], "HZ"}:
            return UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, None
        if unit == UNITS["TEMPERATURE"]:
            return UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, None
        if unit == UNITS["PERCENTAGE"]:
            return UNITS["PERCENTAGE"], None, None
        if unit == UNITS["APPARENT_POWER"]:
            device_class = getattr(SensorDeviceClass, "APPARENT_POWER", None)
            return unit, device_class, None

        return unit, None, None

    def _apply_sensor_traits(
        self, sensor_config: dict[str, Any], initial_data_point: dict[str, Any]
    ) -> None:
        """Apply additional metadata such as state class and icons."""
        if sensor_config.get("device_class") == "enum":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = self._build_enum_options(
                sensor_config, initial_data_point
            )
        elif sensor_config.get("device_class") == "timestamp":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

        state_class = sensor_config.get("state_class")
        if state_class == "measurement":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif state_class == "total_increasing":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        icon = sensor_config.get("icon")
        if icon:
            self._attr_icon = str(icon)

        # SENSOR_TYPES says which sensors are diagnostic, and it is the only
        # place that does. A second list here named seven titles while
        # thirteen entries declared it, so the nameplate ratings and the grid
        # reconnect timer were published as ordinary sensors, and one name in
        # the list ("Battery Type") was not a sensor key at all.
        if sensor_config.get("entity_category") == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            _LOGGER.debug(
                "Set entity category to DIAGNOSTIC for sensor %s", self._sensor_type
            )

    def _build_enum_options(
        self, sensor_config: dict[str, Any], initial_data_point: dict[str, Any]
    ) -> list[str]:
        """Build a complete, forward-compatible enum contract."""
        if self._sensor_type in {"Operating mode", "work state"}:
            options = get_all_operating_modes()
        elif self._sensor_type == "Output priority":
            options = get_all_output_priorities()
        elif self._sensor_type == "Charger Source Priority":
            options = get_all_charger_priorities()
        else:
            options = [str(item) for item in sensor_config.get("options", [])]

        if "Unknown" not in options:
            options.append("Unknown")

        devcode = _normalize_devcode(self._device_meta.get("devcode"))
        transformed_point = initial_data_point
        if devcode is not None and is_devcode_supported(devcode):
            transformed_point = apply_devcode_transformations(
                devcode, initial_data_point.copy()
            )
        initial_value = transformed_point.get("val")
        if initial_value not in (None, "") and str(initial_value) not in options:
            # Firmware occasionally supplies localized or undocumented labels.
            options.append(str(initial_value))
        return options

    @property
    def native_value(self) -> str | float | None:
        """Return the state of the sensor."""
        device_payload = self._get_device_payload()
        if not device_payload:
            return None

        for data_point, devcode in self._matching_data_points(device_payload):
            value = self._extract_transformed_value(data_point, devcode)
            value = self._coerce_native_value(value)
            if value is None:
                continue
            # Keep the entity in VA even when cloud and local readings use
            # different units.
            if (
                self.native_unit_of_measurement == UNITS["APPARENT_POWER"]
                and data_point.get("unit") == "kVA"
                and isinstance(value, float)
            ):
                return value * 1000
            return value
        return None

    def _get_device_payload(self) -> dict[str, Any] | None:
        """Return cached device payload for this sensor."""
        if not self.coordinator.data:
            _LOGGER.debug(
                "No coordinator data available for sensor %s", self._attr_unique_id
            )
            return None

        device_info = self.coordinator.data.get(self._device_sn)
        if not device_info:
            _LOGGER.debug(
                "No device info found for device %s (sensor: %s)",
                self._device_sn,
                self._attr_unique_id,
            )
            return None

        return device_info

    def _matching_data_points(
        self, device_payload: dict[str, Any]
    ) -> Iterator[tuple[dict[str, Any], Any]]:
        """Yield every data point this sensor reads, in the order sent.

        A collector can send one title twice. Devcode 6489 repeats its whole
        dashboard block in the detailed sections, and devcode 6513 reports
        "Input frequency" once as the measured frequency and once as an alarm
        word. Taking the first match alone left a sensor reading unknown for
        as long as the unusable copy arrived first, so the caller walks these
        until one yields a value (#82).
        """
        device_data = device_payload.get("data", [])
        device_meta = device_payload.get("device", {})
        devcode = _normalize_devcode(device_meta.get("devcode"))

        found = False
        for data_point in device_data:
            title = data_point.get("title")
            if (
                isinstance(title, str)
                and normalize_sensor_title(title) in self._source_title_keys
            ):
                found = True
                yield data_point, devcode

        if not found:
            _LOGGER.debug(
                "No matching data point found for sensor %s (looking for: %s)",
                self._attr_unique_id,
                ", ".join(sorted(self._source_titles)),
            )

    def _extract_transformed_value(
        self, data_point: dict[str, Any], devcode: Any
    ) -> Any:
        """Apply devcode transformations and return the raw value."""
        working_point = data_point
        if devcode:
            working_point = apply_devcode_transformations(devcode, data_point.copy())

        return working_point.get("val")

    def _coerce_native_value(self, value: Any) -> str | float | None:
        """Coerce API value into Home Assistant native value format."""
        if self._sensor_type in ENUM_SENSOR_TITLES:
            return self._coerce_enum_value(value)
        if self._sensor_type in TEXT_SENSOR_TITLES:
            return self._coerce_text_value(value)
        return self._coerce_numeric_value(value)

    def _coerce_enum_value(self, value: Any) -> str:
        """Coerce an enumerated value to a string the option list can carry.

        Home Assistant rejects an enum state that is not in the entity's
        options, and the options are built once from what every devcode maps
        plus the value the entity starts with. A vendor that names a state no
        profile registered therefore took the whole sensor down rather than
        showing one unfamiliar word: devcode 6489's download observed only
        "Battery mode", because the reporter's mains was out when they took
        it, and "Mains mode" would have made the sensor unavailable the moment
        the grid came back (#66). The list is extended instead, bounded so a
        reading misclassified as an enum cannot grow it without end.
        """
        if value is None or value == "":
            return "Unknown"

        text = str(value)
        options = self._attr_options
        if options is None or text in options:
            return text
        if len(options) >= _MAX_ENUM_OPTIONS:
            _LOGGER.warning(
                "Sensor %s reports %r and already offers %d options, so it "
                "reads Unknown; this reading is probably not an enumeration",
                self._attr_unique_id,
                text,
                len(options),
            )
            return "Unknown"

        options.append(text)
        _LOGGER.info(
            "Sensor %s reports %r, which no devcode registers; adding it to "
            "the options this entity offers",
            self._attr_unique_id,
            text,
        )
        return text

    @staticmethod
    def _coerce_text_value(value: Any) -> str | None:
        """Return a free-form reading as text, or None when it is absent."""
        if value is None or value == "":
            return None
        return str(value)

    def _coerce_numeric_value(self, value: Any) -> float | str | None:
        """Attempt to coerce sensor value into a float when possible."""
        if value in (None, ""):
            return value

        if isinstance(value, str):
            stripped_value = value.strip()

            if (
                self._sensor_type == "Output Voltage Setting"
                and stripped_value.endswith("V")
            ):
                stripped_value = stripped_value[:-1].strip()

            # DessMonitor sometimes returns "-" (or similar placeholders) when a value is
            # not available. Treat these as unknown to avoid HA numeric parsing errors.
            placeholder_values = {"-", "--", "—"}
            if stripped_value in placeholder_values or stripped_value.lower() in {
                "n/a",
                "na",
                "null",
                "none",
            }:
                _LOGGER.debug(
                    "Treating placeholder value as None for sensor %s: %s",
                    self._attr_unique_id,
                    value,
                )
                return None

            value = stripped_value if stripped_value else value

        try:
            return float(value)
        except (ValueError, TypeError) as err:
            _LOGGER.debug(
                "Could not convert value to float for sensor %s: %s (%s)",
                self._attr_unique_id,
                value,
                err,
            )
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return None

        device_info = self.coordinator.data.get(self._device_sn)
        if not device_info:
            return None

        device_data = device_info.get("data", [])
        device = device_info.get("device", {})
        devcode = _normalize_devcode(device.get("devcode"))

        attrs = {}
        for data_point in device_data:
            original_title = data_point.get("title")

            if original_title == "Timestamp":
                attrs["last_updated"] = data_point.get("val")
            elif original_title == "Operating mode":
                # Apply transformations for operating mode display value
                if devcode:
                    transformed_point = apply_devcode_transformations(
                        devcode, data_point.copy()
                    )
                    attrs["operating_mode"] = transformed_point.get("val")
                else:
                    attrs["operating_mode"] = data_point.get("val")

        return attrs if attrs else None


class DessMonitorLastReadingSensor(DessMonitorSensor):
    """When this integration last saw a device report something new.

    The vendor cloud answers ``queryDeviceLastData`` with the reading it
    stored before a collector went quiet. The fetch succeeds, the device stays
    in the snapshot, Data Source still says ``Cloud``, and every entity goes
    on publishing values that are no longer live - which is what #78 was filed
    for, after a reporter's collector dropped off Wi-Fi and their automations
    kept acting on the numbers.

    What this does not do is decide anything for anybody. Marking measurement
    entities unavailable past some age is the obvious lever and the wrong one:
    it would change what 13,000 installations publish, on a threshold nobody
    has the evidence to pick, and entities going unavailable is the symptom
    #54 and #55 were filed for. So this is additive - one diagnostic sensor,
    no existing entity touched - and the threshold belongs to the automation
    that reads it.

    The value is this host's clock, never the vendor's. The payload's own
    Timestamp is the inverter's wall clock in a timezone this integration
    deliberately does not assume, which is also why the clock controls are
    text entities; comparing it against ``now()`` would mark every device on
    an account offline for the sake of a timezone. What is used instead is
    that the string *changes*: a collector taken off the network held
    ``2026-11-16 18:26:52`` for its whole outage and advanced it on the next
    frame, so movement is the signal and this records when it last moved.

    On startup, and on a device that has not moved since, the state is the
    time this integration first saw the reading. The age it implies is
    therefore a lower bound, which ``observed_change`` says plainly rather
    than leaving to be guessed at.
    """

    def __init__(
        self,
        coordinator: DessMonitorDataUpdateCoordinator,
        device_sn: str,
        device_meta: dict[str, Any],
        collector_meta: dict[str, Any],
    ) -> None:
        """Start the measurement from the reading the device reports now."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_meta=device_meta,
            collector_meta=collector_meta,
            sensor_type=LAST_READING_KEY,
            data_point={"title": LAST_READING_KEY, "val": None},
            source_titles={LAST_READING_KEY},
        )
        self._stamp: str | None = None
        self._seen_at: datetime = dt_util.utcnow()
        self._observed_change = False
        self._note_reported_stamp()

    def _note_reported_stamp(self) -> None:
        """Record the stamp this device reports now, and when it changed."""
        stamp = self._reported_stamp()
        if stamp is None or stamp == self._stamp:
            return
        if self._stamp is not None:
            self._observed_change = True
        self._stamp = stamp
        self._seen_at = dt_util.utcnow()

    def _reported_stamp(self) -> str | None:
        """Return the vendor timestamp in this device's current payload."""
        payload = self._get_device_payload() or {}
        for point in payload.get("data", []):
            if not isinstance(point, dict):
                continue
            if not _is_timestamp_title(point.get("title")):
                continue
            value = point.get("val")
            if value in (None, ""):
                continue
            return str(value)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Measure before publishing, so the state is this cycle's answer."""
        self._note_reported_stamp()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> datetime:  # type: ignore[override]
        """Return when this device last reported something new."""
        return self._seen_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Report what the measurement is made of, not just its result."""
        return {
            # The vendor's own string, unparsed and in its own timezone.
            "payload_timestamp": self._stamp,
            # False until the string has been seen to move, which means the
            # state is the time this integration started watching rather than
            # the time the device reported.
            "observed_change": self._observed_change,
        }
