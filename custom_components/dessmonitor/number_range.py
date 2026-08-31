"""Pure helpers for deriving number-entity slider range and step.

Kept free of Home Assistant imports so the logic can be unit-tested in
isolation. See ``number.py`` for the entity that consumes it.
"""

from __future__ import annotations

import re

# Units whose controls are adjusted in fine increments and whose values are
# never negative (voltages, currents).
_VOLT_AMP = ("V", "A")

# Fallback max for a V/A control without a trustworthy API hint. One current
# value cannot reveal the hardware's configurable range, so the fallback must
# not move with the setting cached at startup (issue #30).
_UNIT_FALLBACK_MAX = {"V": 100.0, "A": 200.0}

# Match a complete hint rather than pulling arbitrary digit fragments from a
# malformed string. DessMonitor uses tilde and several dash variants depending
# on device firmware and localization.
_HINT_RANGE_RE = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*[~\-–—]\s*" r"(-?\d+(?:\.\d+)?)\s*[A-Za-z%°]*\s*$"
)


def parse_hint_range(hint: str) -> tuple[float | None, float | None]:
    """Parse min/max from a hint string like '60.0~66V' or '0-900min'."""
    match = _HINT_RANGE_RE.match(hint)
    if not match:
        return None, None

    try:
        a, b = float(match.group(1)), float(match.group(2))
    except ValueError:
        return None, None
    return min(a, b), max(a, b)


def is_hint_range_usable(hint: str | None, value: float | None) -> bool:
    """Return whether an API hint is complete and consistent with live state."""
    if not hint:
        return False
    lo, hi = parse_hint_range(hint)
    return lo is not None and hi is not None and (value is None or lo <= value <= hi)


def compute_range_and_step(
    unit: str | None, hint: str | None, value: float | None
) -> tuple[float | None, float | None, float]:
    """Compute ``(min, max, step)`` for a value control.

    Step is derived from the unit (``0.1`` for V/A, else ``1.0``) and is always
    returned, otherwise hint-less voltage/current fields fall back to Home
    Assistant's coarse default step of ``1`` (issue #23).

    For the range we trust the API hint only when it is present and actually
    brackets the device's current value. The DessMonitor/SmartESS API has been
    observed returning hints that are wrong or missing for charging-voltage and
    current controls (e.g. a ``25-30V`` hint on a 48V system whose live setting
    is ``57.6V`` (issue #22), or no hint at all so HA defaults to ``0-100``
    (issue #23)). In those cases a range derived from the current setting is
    also unsafe: the setting is a point, not evidence of the hardware limits.
    Voltage/current controls therefore use a stable fallback which is widened
    for unusually large live values. The API remains the final validator for
    device-specific limits.

    A returned ``min`` or ``max`` of ``None`` means "leave HA's default".
    """
    unit = (unit or "").strip()
    step = 0.1 if unit in _VOLT_AMP else 1.0

    lo, hi = parse_hint_range(hint) if hint else (None, None)

    # 1. A complete hint that brackets the live value (or when there is no value
    #    to contradict it) is trusted as-is.
    if is_hint_range_usable(hint, value):
        return lo, hi, step

    # 2. The hint is missing or doesn't cover the live value.
    if unit in _VOLT_AMP:
        fallback_hi = _UNIT_FALLBACK_MAX[unit]
        if value is not None:
            fallback_hi = max(fallback_hi, value + max(abs(value) * 0.5, 5.0))
        if hi is not None:
            fallback_hi = max(fallback_hi, hi)
        return 0.0, round(fallback_hi, 1), step

    if value is not None:
        # For other units we can't guess a sensible magnitude, so only widen an
        # existing hint outward to include the value rather than invent a range.
        if lo is not None and value < lo:
            lo = value
        if hi is not None and value > hi:
            hi = value
        return lo, hi, step

    # 3. No live value to anchor on. For other units leave HA's defaults alone.
    return lo, hi, step
