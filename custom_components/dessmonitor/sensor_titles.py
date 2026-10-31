"""Resolution of raw API sensor titles to canonical sensor definitions.

The cloud and local paths both receive vendor titles that only approximate the
keys in ``SENSOR_TYPES``. Keeping one resolver here means a collector whose
titles carry stray whitespace or a different letter case is understood the same
way wherever its readings arrive from. This module stays free of Home Assistant
imports so maintainer tooling can reuse it.
"""

from __future__ import annotations

import re
from typing import Any, cast

from .const import SENSOR_TYPES

_WHITESPACE = re.compile(r"\s+")


def normalize_sensor_title(value: str) -> str:
    """Return a title reduced to its comparable form.

    Collectors emit titles such as ``"Grid  Power"``; collapsing internal runs
    of whitespace lets them resolve without a per-devcode mapping.
    """
    return _WHITESPACE.sub(" ", value.strip()).lower()


def _build_lookups() -> tuple[dict[str, str], dict[str, str]]:
    """Index the sensor definitions by their normalised key and friendly name."""
    by_key: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for key, config in cast(dict[str, dict[str, Any]], SENSOR_TYPES).items():
        by_key.setdefault(normalize_sensor_title(key), key)
        friendly_name = config.get("name")
        if isinstance(friendly_name, str):
            by_name.setdefault(normalize_sensor_title(friendly_name), key)
    return by_key, by_name


_KEYS_BY_NORMALIZED, _KEYS_BY_FRIENDLY_NAME = _build_lookups()


def resolve_sensor_key(*candidates: str | None) -> str | None:
    """Return the canonical ``SENSOR_TYPES`` key matching the first usable candidate.

    Candidates are tried in the order given, so a devcode-mapped title takes
    precedence over the raw one. A canonical key always wins over another
    entry's friendly name.
    """
    for candidate in candidates:
        if not candidate:
            continue
        if candidate in SENSOR_TYPES:
            return candidate
        normalized = normalize_sensor_title(candidate)
        key = _KEYS_BY_NORMALIZED.get(normalized) or _KEYS_BY_FRIENDLY_NAME.get(
            normalized
        )
        if key:
            return key
    return None


def sensor_display_name(title: str) -> str:
    """Return the normalised entity name a title publishes, or "" for none.

    Two definitions can carry the same friendly name while being separate keys:
    ``energyToday`` and ``Energy Today`` are both shown as "Energy Today".
    Comparing keys treats them as different sensors, so a device that reports
    one of each publishes two entities with one name, which is a duplicate to
    the person reading it.
    """
    key = resolve_sensor_key(title)
    if key is None:
        return ""
    config = cast(dict[str, Any], SENSOR_TYPES[key])
    name = config.get("name")
    return normalize_sensor_title(str(name) if isinstance(name, str) else key)


def sensor_unit(title: str) -> str:
    """Return the canonical unit configured for a title, or an empty string."""
    key = resolve_sensor_key(title)
    if key is None:
        return ""
    return str(cast(dict[str, Any], SENSOR_TYPES[key]).get("unit", ""))
