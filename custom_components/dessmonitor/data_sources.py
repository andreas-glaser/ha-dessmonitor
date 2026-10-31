"""Helpers for explicit live and cached telemetry provenance."""

from __future__ import annotations

import copy
from collections.abc import Container
from typing import Any


def with_data_source(points: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Replace the synthetic data-source point without mutating input."""
    result = [
        copy.deepcopy(point) for point in points if point.get("title") != "Data Source"
    ]
    result.append({"title": "Data Source", "val": source, "unit": ""})
    return result


def snapshot_with_data_source(
    data: dict[str, Any],
    source: str,
    *,
    stale: Container[str] = (),
    stale_source: str = "Cached Cloud",
) -> dict[str, Any]:
    """Copy a coordinator snapshot and label each device's provenance.

    A cloud cycle can succeed for some devices and fail for others, so the
    serials listed in ``stale`` keep the payload a previous cycle fetched and
    are labelled accordingly instead of claiming to be live.
    """
    result = copy.deepcopy(data)
    for serial, payload in result.items():
        if not isinstance(payload, dict):
            continue
        points = payload.get("data", [])
        if isinstance(points, list):
            payload["data"] = with_data_source(
                points, stale_source if serial in stale else source
            )
    return result
