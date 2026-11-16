"""Shared control-value handling, independent of local telemetry pushes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TRANSPORT_CLOUD = "cloud"
TRANSPORT_LOCAL = "local"


@dataclass(frozen=True, slots=True)
class ControlWriteResult:
    """What one accepted control write is known to have achieved.

    ``verified`` is the difference between the two transports. The cloud
    accepts a write and says nothing about whether the inverter applied it, so
    a cloud write reports ``False``. A local write is only reported at all once
    the inverter has acknowledged the command and reported the new value, so it
    reports ``True``.
    """

    value: str
    transport: str
    verified: bool


_MISSING = {
    "",
    "null",
    "none",
    "unknown",
    "unavailable",
    "n/a",
    "na",
    "-",
    "--",
    "nan",
    "inf",
    "+inf",
    "-inf",
    "infinity",
    "+infinity",
    "-infinity",
}


def control_value(raw: Any) -> str | None:
    """Accept scalar values, including zero, without caching API placeholders."""
    if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
        return None
    value = str(raw).strip()
    return None if value.casefold() in _MISSING else value


def _as_number(value: Any) -> float | None:
    """Return a value's numeric form, or None when it is not a number.

    A label such as "60Hz" or "220Vac" is not, which is what keeps the
    comparison below from matching a unit-suffixed label to a bare figure.
    """
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def option_key_for(options: dict[str, Any], value: str) -> str | None:
    """Return the API key an option value corresponds to, or None for no option.

    A vendor does not always report a setting in the spelling it offers for it.
    Devcode 2376 answers 60.0 for an Output Frequency whose options are keyed
    "50.00" and "60.00", and a string comparison never matched, so the select
    read unknown and the field stayed on the list of values to read again on
    every cloud revision - each read a live request to the inverter.

    Keys and labels are compared as given first and only then as numbers, and
    the key is returned in the vendor's own spelling because that is what a
    write has to send.
    """
    for key, label in options.items():
        if value == str(key) or value == str(label):
            return str(key)
    number = _as_number(value)
    if number is None:
        return None
    for key, label in options.items():
        if _as_number(key) == number or _as_number(label) == number:
            return str(key)
    return None


def setting_value(config: dict[str, Any], raw: Any) -> str | None:
    """A select value must be an API key or one of that control's labels."""
    value = control_value(raw)
    if value is None:
        return None
    options = config.get("options", {})
    if config.get("type") == "options" and options:
        allowed = {str(item) for item in (*options.keys(), *options.values())}
        if value in allowed:
            return value
        # Same setting, different spelling: keep the API's key, not the
        # vendor's rendering of it.
        return option_key_for(options, value)
    return value


def cloud_control_snapshot(
    coordinator: Any, serial: str
) -> tuple[object, list[dict[str, Any]]]:
    """Read the original cloud snapshot, never its local-generated Timestamp."""
    cached = getattr(coordinator, "_cached_cloud_data", None)
    if isinstance(cached, dict) and serial in cached:
        points = cached[serial].get("data", [])
        for point in points:
            if point.get("title") == "Timestamp" and point.get("val"):
                return ("timestamp", point["val"]), points
    else:
        points = (coordinator.data or {}).get(serial, {}).get("data", [])
    return ("revision", coordinator.cloud_revision), points


def first_control_value(points: list[dict[str, Any]], *names: str) -> str | None:
    """Return the value of the first named reading that carries one.

    ``find_control_value`` treats its names as a set and so answers with
    whichever reading the payload lists first. Where one title is known to
    carry a control's setting and another its live measurement, that is the
    wrong one half the time, so precedence is decided by the caller's order.
    """
    for name in names:
        value = find_control_value(points, name)
        if value is not None:
            return value
    return None


def find_control_value(points: list[dict[str, Any]], *names: str) -> str | None:
    """Match the exact control name; Main and Current priorities are distinct."""
    wanted = {name.strip().casefold() for name in names}
    for point in points:
        if str(point.get("title", "")).strip().casefold() in wanted:
            value = control_value(point.get("val"))
            if value is not None:
                return value
    return None
