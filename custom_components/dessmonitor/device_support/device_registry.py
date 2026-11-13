"""Device registry for DessMonitor integration.

This module handles registration and lookup of all supported data collector types.
The devcode refers to the data collector/gateway device, not the inverter itself.
It explicitly imports supported devcode modules and provides a unified interface.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Vendor control field names arrive padded or doubly spaced, for example the
# " Inverter Time" that devcode 6515 reports.
_WHITESPACE = re.compile(r"\s+")

# Registry of all supported devcodes
# This is populated by importing devcode modules below
_DEVICE_REGISTRY: dict[int, dict[str, Any]] = {}

# Transformations run for every sensor read; report missing support once per run.
_WARNED_UNSUPPORTED_DEVCODES: set[int] = set()

# Reading scales already reported, as (devcode, title). This runs for every
# reading on every refresh, so the log line is emitted once per reading rather
# than per sample. It is the only trace a scale leaves: the support report
# records the reading with its converted value and the sensor's own unit, so a
# download cannot show that a conversion happened. If a collector ever labels
# a reading Wh while sending kilowatt-hours, this is the line that says which
# reading was divided and on whose authority.
_REPORTED_SCALES: set[tuple[Any, str]] = set()


def _register_devcode(devcode: int, config: dict[str, Any]) -> None:
    """Register a devcode configuration."""
    _DEVICE_REGISTRY[devcode] = config
    _LOGGER.debug("Registered devcode %s: %s", devcode, config["device_info"]["name"])


def _load_device_configurations() -> None:
    """Load all device configurations from devcode files."""
    try:
        # Import devcode 2361 configuration
        from .devcode_2361 import DEVCODE_CONFIG as config_2361

        _register_devcode(2361, config_2361)

        # Import devcode 2376 configuration
        from .devcode_2376 import DEVCODE_CONFIG as config_2376

        _register_devcode(2376, config_2376)

        from .devcode_6416 import DEVCODE_CONFIG as config_6416

        _register_devcode(6416, config_6416)

        from .devcode_6422 import DEVCODE_CONFIG as config_6422

        _register_devcode(6422, config_6422)

        from .devcode_2451 import DEVCODE_CONFIG as config_2451

        _register_devcode(2451, config_2451)

        from .devcode_2449 import DEVCODE_CONFIG as config_2449

        _register_devcode(2449, config_2449)

        from .devcode_2334 import DEVCODE_CONFIG as config_2334

        _register_devcode(2334, config_2334)

        from .devcode_6544 import DEVCODE_CONFIG as config_6544

        _register_devcode(6544, config_6544)

        from .devcode_6514 import DEVCODE_CONFIG as config_6514

        _register_devcode(6514, config_6514)

        from .devcode_6515 import DEVCODE_CONFIG as config_6515

        _register_devcode(6515, config_6515)

        from .devcode_2452 import DEVCODE_CONFIG as config_2452

        _register_devcode(2452, config_2452)

        from .devcode_2428 import DEVCODE_CONFIG as config_2428

        _register_devcode(2428, config_2428)

        from .devcode_2341 import DEVCODE_CONFIG as config_2341

        _register_devcode(2341, config_2341)

        from .devcode_2548 import DEVCODE_CONFIG as config_2548

        _register_devcode(2548, config_2548)

        from .devcode_2477 import DEVCODE_CONFIG as config_2477

        _register_devcode(2477, config_2477)

        from .devcode_2507 import DEVCODE_CONFIG as config_2507

        _register_devcode(2507, config_2507)

        from .devcode_518 import DEVCODE_CONFIG as config_518

        _register_devcode(518, config_518)

        from .devcode_632 import DEVCODE_CONFIG as config_632

        _register_devcode(632, config_632)

        from .devcode_684 import DEVCODE_CONFIG as config_684

        _register_devcode(684, config_684)

        from .devcode_697 import DEVCODE_CONFIG as config_697

        _register_devcode(697, config_697)

        from .devcode_4743 import DEVCODE_CONFIG as config_4743

        _register_devcode(4743, config_4743)

        from .devcode_6489 import DEVCODE_CONFIG as config_6489

        _register_devcode(6489, config_6489)

    except ImportError as err:
        _LOGGER.error("Failed to import device configuration: %s", err)


# Load configurations on module import
_load_device_configurations()


def get_devcode_config(devcode: int) -> dict[str, Any] | None:
    """Get complete configuration for a devcode."""
    return _DEVICE_REGISTRY.get(devcode)


def get_supported_devcodes() -> list[int]:
    """Get list of all supported data collector codes."""
    return list(_DEVICE_REGISTRY.keys())


def is_devcode_supported(devcode: int) -> bool:
    """Check if a devcode is supported by the integration."""
    return devcode in _DEVICE_REGISTRY


def get_device_model_name(devcode: int) -> str:
    """Get human-readable data collector model name for a devcode."""
    config = get_devcode_config(devcode)
    if config:
        return config["device_info"]["name"]
    return f"Unsupported Device (devcode {devcode})"


def map_sensor_title(devcode: int, api_title: str) -> str:
    """Map API sensor title to standardized display name based on devcode."""
    config = get_devcode_config(devcode)
    if not config:
        _LOGGER.debug(
            "Unknown devcode %s, using original title: %s", devcode, api_title
        )
        return api_title

    # Get title mappings for this devcode
    title_mappings = config.get("sensor_title_mappings", {})

    # Apply mapping if exists, otherwise use original
    mapped_title = title_mappings.get(api_title, api_title)

    return mapped_title


def map_control_field(devcode: int, api_field_name: str) -> str:
    """Map an API control field name to its display name for this devcode.

    The name is trimmed and its internal whitespace collapsed first, so a
    padded vendor name neither reaches an entity nor has to be matched with its
    padding in a devcode mapping.
    """
    field_name = _WHITESPACE.sub(" ", api_field_name).strip()
    config = get_devcode_config(devcode)
    if not config:
        return field_name

    control_mappings = config.get("control_field_mappings", {})
    return control_mappings.get(field_name, field_name)


def _as_devcode(devcode: Any) -> int | None:
    """Return a devcode as the registry keys it, or None when it is not one.

    The cloud payload carries the devcode as a number for some accounts and as
    a string for others, and both reach these lookups.
    """
    try:
        return int(devcode)
    except (TypeError, ValueError):
        return None


def devcode_has_temporal_controls(devcode: Any) -> bool:
    """Return whether this devcode declares any temporal control.

    Discovery asks before fetching a device's control fields, so a devcode
    with no temporal control costs no cloud request.
    """
    return bool(_temporal_controls(devcode))


def temporal_control_kind(devcode: Any, field_id: Any) -> str | None:
    """Return the platform a control field belongs on: time, text or neither.

    Only fields a devcode profile declares are reclassified. A field id means
    different things on different devcodes, so the profile that reported it
    owns the mapping, and an unlisted field stays on the number platform.
    """
    if not isinstance(field_id, str):
        return None
    return _temporal_controls(devcode).get(field_id)


def _temporal_controls(devcode: Any) -> dict[str, str]:
    """Return the temporal control fields a devcode profile declares."""
    key = _as_devcode(devcode)
    config = get_devcode_config(key) if key is not None else None
    if not config:
        return {}
    controls = config.get("temporal_controls")
    return controls if isinstance(controls, dict) else {}


def control_value_reading(devcode: Any, field_id: Any) -> str | None:
    """Return the reading title that carries a control's value, if declared.

    A collector may answer a control's own name with a live measurement rather
    than the setting: devcode 2376 reports 229.8 V for the Output Voltage
    control while the setpoint sits in its "Output Voltage Setting" reading
    (#61). Seeding from the measurement would show a setting the inverter does
    not have, and seeding from nothing leaves the field on the list of values
    to read again on every cloud revision, each read a live request over the
    collector's single-transaction link.

    The profile that reported the collector declares the title, from committed
    evidence. A value found this way is still checked against the control's
    options before it reaches an entity, so a wrong declaration leaves the
    control unread rather than showing a value the inverter never had.
    """
    key = _as_devcode(devcode)
    config = get_devcode_config(key) if key is not None else None
    if not config or not isinstance(field_id, str):
        return None
    declared = config.get("control_value_readings")
    if not isinstance(declared, dict):
        return None
    title = declared.get(field_id)
    return title if isinstance(title, str) and title.strip() else None


def local_control_setting(devcode: Any, field_id: Any) -> str | None:
    """Return the local setting a cloud control writes, if a profile declares it.

    A cloud control is identified by a platform field id such as
    ``bat_charging_float_voltage``, and a local setting by the key of the
    command that writes it. Nothing connects the two but evidence: a
    diagnostics download that shows the cloud control and the inverter's own
    rating reply carrying the same value under names that are not spelled
    alike. Where the two names do normalise to the same thing, the hybrid
    coordinator pairs them itself; this is for the rest, and a declaration here
    always wins.

    Pairing is what decides which transport a write takes, so a wrong entry
    would write the wrong setting. The local write is still verified against
    the setting it names, so a mistake is reported rather than cached, but the
    inverter would already have been changed - declare only from a download.
    """
    key = _as_devcode(devcode)
    config = get_devcode_config(key) if key is not None else None
    if not config or not isinstance(field_id, str):
        return None
    declared = config.get("local_control_settings")
    if not isinstance(declared, dict):
        return None
    setting = declared.get(field_id)
    return setting if isinstance(setting, str) and setting.strip() else None


def filter_control_options(
    devcode: int,
    param_id: str,
    options: dict[str, str],
    data: list[dict[str, Any]],
) -> dict[str, str]:
    """Apply a device-specific option filter when its hardware requires one."""
    config = get_devcode_config(devcode)
    option_filter = config.get("control_options_filter") if config else None
    if option_filter is None:
        return options
    return option_filter(param_id, options, data)


def map_output_priority(devcode: int, api_value: str) -> str:
    """Map output priority value to human-readable format based on devcode."""
    config = get_devcode_config(devcode)
    if not config:
        return api_value

    priority_mappings = config.get("output_priority_mapping", {})
    return priority_mappings.get(api_value, api_value)


def map_charger_priority(devcode: int, api_value: str) -> str:
    """Map charger priority value to human-readable format based on devcode."""
    config = get_devcode_config(devcode)
    if not config:
        return api_value

    charger_mappings = config.get("charger_priority_mapping", {})
    return charger_mappings.get(api_value, api_value)


def map_operating_mode(devcode: int, api_value: str) -> str:
    """Map operating mode value to human-readable format based on devcode."""
    config = get_devcode_config(devcode)
    if not config:
        return api_value

    mode_mappings = config.get("operating_mode_mapping", {})
    if not isinstance(api_value, str):
        return api_value

    normalized_value = api_value.strip()

    if normalized_value in mode_mappings:
        return mode_mappings[normalized_value]

    for candidate, mapped_value in mode_mappings.items():
        if (
            isinstance(candidate, str)
            and candidate.lower().strip() == normalized_value.lower()
        ):
            return mapped_value

    return normalized_value


# How to reach a canonical sensor's unit from the unit a collector declares.
# Keyed by (declared unit, canonical unit), both casefolded, and holding the
# scale as a numerator and a denominator rather than a float: a lifetime
# counter goes into long-term statistics, and multiplying 15.0452 MWh by 1000.0
# yields 15045.199999999999 where dividing keeps the figure the vendor sent.
#
# Only the energy scales are listed, because those are the only ones any
# evidence in this repository shows a collector disagreeing with the sensor
# about, and a factor applied to a reading that did not need one is a
# thousand-fold error in the other direction. Add a pair here when a committed
# download shows it, not in anticipation.
_UNIT_SCALES: dict[tuple[str, str], tuple[int, int]] = {
    ("wh", "kwh"): (1, 1000),
}


def declared_reading_unit(devcode: Any, title: str) -> str:
    """Return the unit a profile says this reading arrives in, or "".

    A collector normally labels its own readings, and that label is the
    evidence used. This covers the case where it sends the value and no unit:
    the profile states what the vendor's own download showed, so a payload
    that happens to omit the unit does not silently go unscaled.
    """
    key = _as_devcode(devcode)
    config = get_devcode_config(key) if key is not None else None
    if not config:
        return ""
    declared = config.get("source_units") or {}
    normalized = _normalize_title(title)
    for name, unit in declared.items():
        if _normalize_title(name) == normalized:
            return str(unit)
    return ""


def normalize_reading_scale(devcode: Any, transformed_data: dict[str, Any]) -> None:
    """Scale a reading whose declared unit is a multiple of its sensor's unit.

    An entity's unit comes from ``SENSOR_TYPES`` and never from the payload, so
    a collector that reports watt-hours on a reading this integration publishes
    in kilowatt-hours puts a figure a thousand times too large on the energy
    dashboard, where it also lands in long-term statistics. Devcode 2449
    reported 15045200 Wh of lifetime generation as 15045200 kWh (#71), and
    devcode 2452 reported the same thing a devcode-specific callback had to
    correct by hand.

    Deciding it from the unit the collector declares fixes the whole class and
    cannot misfire on a collector that already reports the canonical unit,
    which a blanket per-title conversion can. It runs for every devcode,
    including one with no profile, because the vendor's own label is the
    evidence rather than anything a profile knows.
    """
    from ..sensor_titles import sensor_unit

    title = transformed_data.get("title")
    value = transformed_data.get("val")
    if not isinstance(title, str) or value is None:
        return
    declared = str(
        transformed_data.get("unit") or declared_reading_unit(devcode, title)
    ).strip()
    if not declared:
        return
    canonical = sensor_unit(title).strip()
    if not canonical:
        return
    scale = _UNIT_SCALES.get((declared.casefold(), canonical.casefold()))
    if scale is None:
        return
    numerator, denominator = scale
    try:
        scaled = float(str(value).strip()) * numerator / denominator
    except (TypeError, ValueError):
        # Not a number, so not a reading a scale applies to. The support
        # report still records it as the collector sent it.
        return
    seen = (devcode, _normalize_title(title))
    if seen not in _REPORTED_SCALES:
        _REPORTED_SCALES.add(seen)
        _LOGGER.debug(
            "Devcode %s reports %s in %s and the sensor publishes %s, so its "
            "values are scaled by %s/%s (%s became %s). The unit the collector "
            "declared is what decided this%s",
            devcode,
            title,
            declared,
            canonical,
            numerator,
            denominator,
            value,
            scaled,
            (
                ""
                if transformed_data.get("unit")
                else "; the payload carried no unit, so the profile's own "
                "declaration was used"
            ),
        )
    transformed_data["val"] = scaled
    # The reading now carries the unit its sensor publishes, so the support
    # report and a second pass over the same point both agree with the entity.
    transformed_data["unit"] = canonical


def apply_devcode_transformations(
    devcode: int, sensor_data: dict[str, Any]
) -> dict[str, Any]:
    """Apply all devcode-specific transformations to sensor data."""
    config = get_devcode_config(devcode)
    if not config:
        if devcode not in _WARNED_UNSUPPORTED_DEVCODES:
            _LOGGER.warning(
                "Unsupported devcode %s - no device-specific mappings available. "
                "Using raw sensor titles and values; sensor support may be limited. "
                "To request or add support, share a CLI analysis JSON and your "
                "inverter model as described at "
                "https://github.com/andreas-glaser/ha-dessmonitor/blob/dev/"
                "docs/ADDING_DEVCODES.md#request-support "
                "(logged once per devcode until Home Assistant restarts)",
                devcode,
            )
            _WARNED_UNSUPPORTED_DEVCODES.add(devcode)
        # A collector with no profile still labels its readings, and the
        # titles that already resolve without one still reach an entity.
        transformed_data = sensor_data.copy()
        normalize_reading_scale(devcode, transformed_data)
        return transformed_data

    transformed_data = sensor_data.copy()

    _apply_title_mapping(devcode, transformed_data)
    normalize_reading_scale(devcode, transformed_data)
    _apply_value_mappings(devcode, transformed_data)
    _apply_custom_transformations(config, transformed_data)

    return transformed_data


def _apply_title_mapping(devcode: int, transformed_data: dict[str, Any]) -> None:
    """Map sensor title to configured alias when available."""
    if "title" not in transformed_data:
        return

    original_title = transformed_data["title"]
    transformed_data["title"] = map_sensor_title(devcode, original_title)


def _apply_value_mappings(devcode: int, transformed_data: dict[str, Any]) -> None:
    """Apply built-in value mappings such as priorities and modes."""
    title = transformed_data.get("title")
    value = transformed_data.get("val")
    if title is None or value is None:
        return

    normalized = title.lower()
    if "priority" in normalized and "output" in normalized:
        transformed_data["val"] = map_output_priority(devcode, str(value))
    elif "priority" in normalized and "charg" in normalized:
        transformed_data["val"] = map_charger_priority(devcode, str(value))
    elif "operating mode" in normalized or normalized.endswith(" mode"):
        transformed_data["val"] = map_operating_mode(devcode, str(value))


def _apply_custom_transformations(
    config: dict[str, Any], transformed_data: dict[str, Any]
) -> None:
    """Apply custom transformation callbacks defined by the devcode config."""
    title = transformed_data.get("title")
    if not title:
        return

    value_transformations = config.get("value_transformations", {})
    transform_func = value_transformations.get(title)
    if not transform_func:
        return

    try:
        transformed_data["val"] = transform_func(transformed_data.get("val"))
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Value transformation failed for %s: %s",
            title,
            err,
        )


def get_device_capabilities(devcode: int) -> list[str]:
    """Get list of supported features for a devcode."""
    config = get_devcode_config(devcode)
    if config:
        return config["device_info"].get("supported_features", [])
    return []


def get_parameter_sensor_names(devcode: int) -> set[str]:
    """Return the set of parameter names to fetch from queryDeviceParsEs."""
    config = get_devcode_config(devcode)
    if config:
        return config.get("parameter_sensor_names", set())
    return set()


def needs_parameter_fetch(devcode: int) -> bool:
    """Check whether a devcode requires an extra parameter fetch."""
    return bool(get_parameter_sensor_names(devcode))


def is_setting_reading(devcode: Any, title: str) -> bool:
    """Return whether a profile declares this title a setting, not a reading.

    Several collectors return the inverter's own setpoints in the telemetry
    call: devcode 2452 reports the battery recharge, bulk and float voltages
    beside the live readings, and five of them are the values of controls the
    account already publishes as number and select entities. They carry a unit,
    so the support report counted them among the readings that reach no entity
    and told the owner that fourteen readings were missing when none were (#53).

    A profile declares them explicitly, from committed evidence, rather than
    being guessed at from the control template: an account whose control
    template cannot be read still gets the right answer.
    """
    key = _as_devcode(devcode)
    config = get_devcode_config(key) if key is not None else None
    if not config:
        return False
    declared = config.get("setting_readings")
    if not declared:
        return False
    return _normalize_title(title) in {_normalize_title(name) for name in declared}


def absent_reading_reason(devcode: Any, title: str) -> str | None:
    """Return why a profile declares this title carries no reading, or None.

    Several collectors report every field their protocol defines whether the
    hardware fills it or not: devcode 4743 reports the S and T phases of a unit
    whose own ``InverterType`` reads ``Single-phase Grid-Connected Inverter``,
    and a per-string PV power that stays at 0 while the string produces 1552 W.
    They carry a unit, so the support report counted them among the readings
    that reach no entity and told the owner that sixteen readings were missing
    when none were (#58).

    Mapping them instead would publish sensors that read zero forever, which is
    worse than no sensor. So the profile states the decision and the evidence
    for it, in one place the Repairs evaluation, the diagnostics download,
    ``tools/analysis_coverage.py`` and the coverage guard all read. A guess
    would hide a genuine gap, which is the failure this guard exists to catch,
    so each entry names what was measured.
    """
    key = _as_devcode(devcode)
    config = get_devcode_config(key) if key is not None else None
    if not config:
        return None
    declared = config.get("absent_readings") or {}
    normalized = _normalize_title(title)
    for name, reason in declared.items():
        if _normalize_title(name) == normalized:
            return str(reason)
    return None


def is_absent_reading(devcode: Any, title: str) -> bool:
    """Return whether a profile declares this title carries no reading."""
    return absent_reading_reason(devcode, title) is not None


def _normalize_title(title: Any) -> str:
    """Compare titles the way the shared sensor resolver does."""
    return " ".join(str(title).split()).casefold()


def get_all_operating_modes() -> list[str]:
    """Get all possible operating mode values from base modes and all devcode transformations."""
    from ..const import OPERATING_MODES

    # Start with base operating modes
    all_modes = set(OPERATING_MODES)

    # Add transformed values from all registered devcodes
    for devcode, config in _DEVICE_REGISTRY.items():
        operating_mode_mapping = config.get("operating_mode_mapping", {})
        # Add both original API values and transformed values
        all_modes.update(operating_mode_mapping.keys())
        all_modes.update(operating_mode_mapping.values())

    return sorted(all_modes)


def _get_all_priority_values(base_values: list[str], mapping_name: str) -> list[str]:
    """Return every known raw and mapped value for a priority sensor."""
    values = set(base_values)
    values.add("Unknown")
    for config in _DEVICE_REGISTRY.values():
        priority_mapping = config.get(mapping_name, {})
        values.update(str(value) for value in priority_mapping.keys())
        values.update(str(value) for value in priority_mapping.values())
    return sorted(values)


def get_all_output_priorities() -> list[str]:
    """Return every output-priority value known across supported devices."""
    from ..const import OUTPUT_PRIORITIES

    return _get_all_priority_values(OUTPUT_PRIORITIES, "output_priority_mapping")


def get_all_charger_priorities() -> list[str]:
    """Return every charger-priority value known across supported devices."""
    from ..const import CHARGER_PRIORITIES

    return _get_all_priority_values(CHARGER_PRIORITIES, "charger_priority_mapping")


def get_registry_info() -> dict[str, Any]:
    """Get information about all registered devices."""
    return {
        "supported_devcodes": get_supported_devcodes(),
        "total_devices": len(_DEVICE_REGISTRY),
        "devices": {
            devcode: {
                "name": config["device_info"]["name"],
                "description": config["device_info"].get("description", ""),
                "features": config["device_info"].get("supported_features", []),
            }
            for devcode, config in _DEVICE_REGISTRY.items()
        },
    }
