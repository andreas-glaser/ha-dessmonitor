"""Helpers for explicit live and cached telemetry provenance."""

from __future__ import annotations

import copy
from typing import Any


def with_data_source(points: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Replace the synthetic data-source point without mutating input."""
    result = [
        copy.deepcopy(point) for point in points if point.get("title") != "Data Source"
    ]
    result.append({"title": "Data Source", "val": source, "unit": ""})
    return result


def snapshot_with_data_source(data: dict[str, Any], source: str) -> dict[str, Any]:
    """Copy a coordinator snapshot and label each device's provenance."""
    result = copy.deepcopy(data)
    for payload in result.values():
        if isinstance(payload, dict):
            points = payload.get("data", [])
            if isinstance(points, list):
                payload["data"] = with_data_source(points, source)
    return result
