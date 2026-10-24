"""Shared control-value handling, independent of local telemetry pushes."""

from __future__ import annotations

from typing import Any

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


def setting_value(config: dict[str, Any], raw: Any) -> str | None:
    """A select value must be an API key or one of that control's labels."""
    value = control_value(raw)
    options = config.get("options", {})
    if config.get("type") == "options" and options:
        allowed = {str(item) for item in (*options.keys(), *options.values())}
        if value not in allowed:
            return None
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


def find_control_value(points: list[dict[str, Any]], *names: str) -> str | None:
    """Match the exact control name; Main and Current priorities are distinct."""
    wanted = {name.strip().casefold() for name in names}
    for point in points:
        if str(point.get("title", "")).strip().casefold() in wanted:
            value = control_value(point.get("val"))
            if value is not None:
                return value
    return None
