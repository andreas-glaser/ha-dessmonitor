"""Combine cloud and local evidence into reviewable devcode support data."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

_MAX_REPORT_BYTES = 1_000_000


def load_local_report(path_value: str) -> dict[str, Any]:
    """Load one bounded, regular local-probe JSON report."""
    source_path = Path(path_value).expanduser()
    if source_path.is_symlink():
        raise ValueError("local report must not be a symbolic link")
    path = source_path.resolve(strict=True)
    if not path.is_file():
        raise ValueError("local report must be a regular file")
    if path.stat().st_size > _MAX_REPORT_BYTES:
        raise ValueError("local report exceeds the 1 MB safety limit")
    with path.open("r", encoding="utf-8") as report_file:
        report = json.load(report_file)
    if not isinstance(report, dict):
        raise ValueError("local report must contain a JSON object")
    if report.get("report_version") != 1 or report.get("safety") != "read_only":
        raise ValueError("local report is not a supported read-only probe report")
    if report.get("status", "success") != "success":
        raise ValueError(
            "local report records a failed probe; use it for troubleshooting"
        )
    if not isinstance(report.get("inverters"), list) or not report["inverters"]:
        raise ValueError("local report contains no inverter evidence")
    return report


def combine_evidence(
    cloud_analysis: dict[str, Any],
    local_report: dict[str, Any],
    *,
    inverter_address: int = 1,
) -> dict[str, Any]:
    """Attach sanitized local facts and conservative title correlations."""
    analysis = copy.deepcopy(cloud_analysis)
    matching = [
        inverter
        for inverter in local_report["inverters"]
        if inverter.get("address") == inverter_address
    ]
    if len(matching) != 1:
        raise ValueError(
            f"local report does not contain exactly one inverter at address {inverter_address}"
        )
    inverter = matching[0]
    detected = local_report.get("detected", {})
    local_serial = str(inverter.get("serial", ""))
    cloud_serial = str(analysis.get("device_sn", ""))
    inverter_identity_match = _identity_match(cloud_serial, local_serial)
    collector_identity_match = _redacted_identity_match(
        str(analysis.get("collector_identity", "")),
        str(local_report.get("collector", {}).get("product_number", "")),
    )
    address_match = analysis.get("device_address") == inverter_address
    route_identity_match = collector_identity_match == "matched" and address_match

    local_evidence = {
        "profile": detected.get("profile"),
        "tunnel_device_code": detected.get("tunnel_device_code"),
        "collector_address": detected.get("collector_address"),
        "inverter_address": inverter_address,
        "model": inverter.get("model", ""),
        "firmware": inverter.get("firmware", ""),
        "sensor_count": inverter.get("sensor_count", 0),
        "sensor_titles": sorted(str(title) for title in inverter.get("sensors", {})),
        "identity_match": (
            "matched"
            if inverter_identity_match == "matched" or route_identity_match
            else inverter_identity_match
        ),
        "identity_basis": (
            "inverter_serial"
            if inverter_identity_match == "matched"
            else (
                "collector_product_number_and_address"
                if route_identity_match
                else "unverified"
            )
        ),
    }
    correlations = correlate_sensor_titles(
        analysis.get("sample_data", []), inverter.get("sensors", {})
    )
    analysis["analysis_version"] = 4
    analysis["device_sn"] = analysis.get("device_identity", "redacted")
    analysis["collector_alias"] = "redacted"
    analysis["local_evidence"] = local_evidence
    analysis["sensor_correlations"] = correlations
    analysis["suggested_sensor_title_mappings"] = {
        item["cloud_title"]: item["local_title"]
        for item in correlations
        if item["cloud_title"] != item["local_title"] and item["confidence"] == "high"
    }
    analysis["checksum"] = analysis_checksum(analysis)
    return analysis


def correlate_sensor_titles(
    cloud_points: list[dict[str, Any]], local_sensors: dict[str, Any]
) -> list[dict[str, str]]:
    """Return only unique, high-confidence semantic title matches."""
    local_by_key: dict[str, list[str]] = {}
    for local_title in local_sensors:
        local_by_key.setdefault(_title_key(local_title), []).append(local_title)

    matches: list[dict[str, str]] = []
    for point in cloud_points:
        cloud_title = str(point.get("title", "")).strip()
        if not cloud_title:
            continue
        candidates = local_by_key.get(_title_key(cloud_title), [])
        if len(candidates) != 1:
            continue
        matches.append(
            {
                "cloud_title": cloud_title,
                "local_title": candidates[0],
                "method": "normalized_title",
                "confidence": "high",
            }
        )
    return sorted(matches, key=lambda item: item["cloud_title"].lower())


def analysis_checksum(analysis: dict[str, Any]) -> str:
    """Return the existing deterministic analysis integrity checksum."""
    hashable = {
        key: value
        for key, value in analysis.items()
        if key not in ("device_sn", "checksum")
    }
    return hmac.new(
        b"dessmonitor-analysis-v2",
        json.dumps(hashable, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _identity_match(cloud_serial: str, local_serial: str) -> str:
    """Compare clear or default-hashed identities without exposing either."""
    if not cloud_serial or not local_serial:
        return "unknown"
    cloud_hash = hashlib.sha256(cloud_serial.encode("utf-8")).hexdigest()[:12]
    if local_serial == cloud_serial or local_serial == f"sha256:{cloud_hash}":
        return "matched"
    return "different"


def _redacted_identity_match(first: str, second: str) -> str:
    """Compare already-redacted identities without accepting empty values."""
    if not first or not second:
        return "unknown"
    return "matched" if first == second else "different"


def _title_key(value: str) -> str:
    """Normalize only well-known vendor synonyms; avoid value-based guessing."""
    normalized = value.casefold().replace("termperature", "temperature")
    normalized = re.sub(r"\bac\s+output\b", "output", normalized)
    normalized = re.sub(r"\bmains\b", "grid", normalized)
    normalized = re.sub(r"\bsolar\b", "pv", normalized)
    normalized = re.sub(r"\bbattery percentage\b", "state of charge", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())
