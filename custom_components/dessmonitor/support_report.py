"""The devcode support report, shared by the integration and the CLI.

A reporter should not have to install Python to tell us what their inverter
reports. The integration already makes every call the CLI's ``analyze`` makes,
so this module assembles the same evidence from data the coordinator holds, and
both callers build it here so the two cannot drift (#60).

It holds no Home Assistant imports, so the CLI and the maintainer tooling can
import it, and it performs no I/O: callers pass the readings in and decide what
to do with the report.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from typing import Any

# Intentionally no intra-package imports at module scope. The contributor CLI
# loads this file by path on machines with no Home Assistant installed, where
# importing the integration package would fail, and it only calls the
# redaction and checksum helpers below. The devcode-aware functions import
# what they need when they run, inside Home Assistant or the test suite.

REPORT_VERSION = 4

SUPPORTED = "supported"
PARTIAL = "partial"
UNSUPPORTED = "unsupported"

# Readings the integration publishes as an entity attribute rather than as a
# sensor of their own, so they are not dropped and must not be counted as such.
_ATTRIBUTE_READINGS = {"timestamp"}


def short_identity(value: Any) -> str:
    """Return the correlation form of an identifier, never the identifier.

    Two downloads of the same device carry the same value, so a maintainer can
    tell devices apart across reports without being told a serial number. This
    is correlation, not anonymity: the hash of a known serial is reproducible.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def resolved_key_for(devcode: Any, point: dict[str, Any]) -> str | None:
    """Return the canonical sensor a raw reading reaches, or None.

    This is the predicate that decides whether a reading becomes an entity, and
    it is the one the sensor platform applies. Everything that reports coverage
    asks it here rather than reimplementing it.
    """
    from .device_support import apply_devcode_transformations
    from .sensor_titles import resolve_sensor_key

    title = point.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    mapped = title
    if devcode:
        mapped = apply_devcode_transformations(devcode, dict(point)).get("title", title)
    return resolve_sensor_key(mapped, title)


def build_support_report(
    *,
    devcode: Any,
    readings: list[dict[str, Any]],
    device_serial: Any = None,
    collector_product_number: Any = None,
    device_address: Any = None,
    control_fields: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    local: dict[str, Any] | None = None,
    api_profile: str | None = None,
    integration_version: str | None = None,
    source: str = "integration_diagnostics",
) -> dict[str, Any]:
    """Build one device's support report from readings already in hand.

    ``readings`` are raw cloud or local data points, each with ``title``,
    ``val`` and ``unit``. Every reading carries its unit here, where a CLI
    analysis records one only for the first twenty, so a report built from this
    is the better evidence for the coverage guard (#60).
    """
    reading_rows: list[dict[str, Any]] = []
    unresolved_with_unit: list[dict[str, str]] = []
    unresolved_without_unit: list[str] = []
    resolved_keys: set[str] = set()

    for point in readings:
        title = point.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()
        unit = str(point.get("unit") or "").strip()
        identifying = is_identifier_name(title)
        value = "" if identifying else _as_text(point.get("val"))
        key = resolved_key_for(devcode, point)

        reading_rows.append(
            {"title": title, "value": value, "unit": unit, "resolved_key": key}
        )

        if key:
            resolved_keys.add(key)
        elif title.casefold() in _ATTRIBUTE_READINGS:
            continue
        elif unit:
            unresolved_with_unit.append({"title": title, "unit": unit, "sample": value})
        else:
            unresolved_without_unit.append(title)

    profile = _profile_facts(devcode)
    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "source": source,
        "api_profile": api_profile,
        "integration_version": integration_version,
        "devcode": devcode,
        "device_identity": short_identity(device_serial),
        "collector_identity": short_identity(collector_product_number),
        "device_address": device_address,
        "support": {
            "status": classify_support(devcode, resolved_keys, unresolved_with_unit),
            "profile": profile["name"],
            "known_inverters": profile["known_inverters"],
            "resolved": len(resolved_keys),
            "total": len(reading_rows),
            "unresolved_with_unit": sorted(
                unresolved_with_unit, key=lambda item: item["title"].casefold()
            ),
            "unresolved_without_unit": sorted(
                set(unresolved_without_unit), key=str.casefold
            ),
        },
        "readings": reading_rows,
    }

    if control_fields is not None:
        report["control_fields"] = _redacted_controls(control_fields)
    if parameters is not None:
        report["parameters"] = _redacted_controls(parameters)
    if local is not None:
        report["local"] = local

    report["checksum"] = report_checksum(report)
    return report


def classify_support(
    devcode: Any,
    resolved_keys: set[str],
    unresolved_with_unit: list[dict[str, str]],
) -> str:
    """Classify a devcode as supported, partial or unsupported.

    ``partial`` is the shape that stayed invisible for eight months on devcode
    6514: a profile exists, so nothing warns, while readings the collector
    labels with a unit reach no entity at all (#35, then #56).
    """
    if not _has_profile(devcode):
        return UNSUPPORTED
    if unresolved_with_unit:
        return PARTIAL
    return SUPPORTED


def _has_profile(devcode: Any) -> bool:
    """Return whether a devcode profile is registered, for any devcode form."""
    from .device_support import is_devcode_supported

    try:
        return is_devcode_supported(int(devcode))
    except (TypeError, ValueError):
        return False


def _profile_facts(devcode: Any) -> dict[str, Any]:
    """Return the profile's display name and the inverters it names."""
    from .device_support import get_device_model_name
    from .device_support.device_registry import get_devcode_config

    if not _has_profile(devcode):
        return {"name": None, "known_inverters": []}
    code = int(devcode)
    config = get_devcode_config(code) or {}
    device_info = config.get("device_info", {})
    return {
        "name": get_device_model_name(code),
        "known_inverters": list(device_info.get("known_inverters", [])),
    }


def _redacted_controls(fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Return control metadata as a list, without identifying values."""
    rows: list[dict[str, Any]] = []
    for name, config in fields.items():
        row = {"name": str(name), **copy.deepcopy(config or {})}
        if is_identifier_name(str(name)):
            row["val"] = ""
            row["value"] = ""
        rows.append(row)
    return sorted(rows, key=lambda item: str(item.get("name", "")).casefold())


def _as_text(value: Any) -> str:
    """Return a scalar reading as text, and anything else as empty."""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def redact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Copy an analysis, blank known identifiers, and checksum the result."""
    redacted = copy.deepcopy(analysis)
    redacted["device_sn"] = ""
    redacted["collector_alias"] = ""
    for section, label in (("sample_data", "title"), ("parameters", "name")):
        for point in redacted.get(section, []):
            if is_identifier_name(point.get(label, "")):
                point["value"] = ""
    for title in redacted.get("unit_patterns", {}):
        if is_identifier_name(title):
            redacted["unit_patterns"][title] = []
    # Nested values remain covered by the checksum; redact before signing.
    redacted["checksum"] = analysis_checksum(redacted)
    return redacted


def is_identifier_name(name: str) -> bool:
    """Recognize vendor identity labels, including 'devise serial number'."""
    normalized = re.sub(r"[^a-z0-9]", "", str(name).casefold())
    return normalized in {
        "id",
        "recordid",
        "deviceid",
        "collectorid",
        "inverterid",
        "plantid",
        "stationid",
        "sn",
        "devicesn",
        "collectorsn",
        "invertersn",
        "pn",
        "collectorpn",
        "mac",
        "ip",
        "username",
        "email",
    } or normalized.endswith(
        (
            "serialnumber",
            "serialno",
            "serial",
            "alias",
            "productnumber",
            "macaddress",
            "ipaddress",
            "ssid",
            "password",
            "token",
            "secret",
        )
    )


def analysis_checksum(
    analysis: dict[str, Any], *, include_collector_alias: bool = False
) -> str:
    """Hash report data while allowing personal identifiers to be redacted.

    Including the alias is only for verifying reports from older CLI versions.
    """
    excluded = {"device_sn", "checksum"}
    if not include_collector_alias:
        excluded.add("collector_alias")
    hashable = {key: value for key, value in analysis.items() if key not in excluded}
    return hmac.new(
        b"dessmonitor-analysis-v2",
        json.dumps(hashable, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def report_checksum(report: dict[str, Any]) -> str:
    """Checksum a support report over everything but the checksum itself.

    The key is in the repository, so this detects an edited file rather than
    proving where a report came from. ``source`` records that.
    """
    hashable = {key: value for key, value in report.items() if key != "checksum"}
    return hmac.new(
        b"dessmonitor-analysis-v2",
        json.dumps(hashable, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
