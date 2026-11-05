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

# 7 says how many rows each exclusion accounts for, under ``excluded``, and
# counts the unresolved rows, so resolved + unresolved == total exactly. Three
# classes of row are now left out of ``total`` - nothing, attributes and
# declared settings - and without the breakdown a reader cannot reconstruct
# "maps N of M readings", which is the complaint that produced version 5.
# 6 leaves a reading a profile declares a setting out of both counts, the way
# an entity attribute already was: devcode 2452 returns the inverter's own
# setpoints beside its telemetry, five of them the values of controls the
# account publishes as number and select entities, and counting them as
# readings that reach no entity told the owner fourteen were missing (#53).
# 5 counts readings consistently: ``resolved`` and ``total`` are both reading
# counts, so "maps N of M readings" is arithmetic a reader can check, and the
# number of distinct entities those readings reach is reported separately.
# Version 4 counted distinct entity keys against raw rows, which made a device
# whose collector repeats a title look as if readings were being dropped.
REPORT_VERSION = 7

SUPPORTED = "supported"
PARTIAL = "partial"
UNSUPPORTED = "unsupported"

# Readings the integration publishes as an entity attribute rather than as a
# sensor of their own, so they are not dropped and must not be counted as such.
_ATTRIBUTE_READINGS = {"timestamp"}


def is_attribute_reading(title: str) -> bool:
    """Return whether a reading reaches Home Assistant as other than a sensor.

    The Timestamp is published as an attribute of every entity, and an
    identity field names the hardware rather than measuring it. Neither is a
    reading being dropped, so neither belongs in a count of readings that
    reach nothing: devcode 2376 reports "devise serial number" beside its
    telemetry and the report counted it among three readings it said reached
    no entity, of which only one really did.
    """
    return title.strip().casefold() in _ATTRIBUTE_READINGS or is_identifier_name(title)


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
    from .device_support import is_setting_reading

    reading_rows: list[dict[str, Any]] = []
    unresolved_with_unit: list[dict[str, str]] = []
    unresolved_without_unit: list[str] = []
    resolved_keys: set[str] = set()
    # Rows, not titles: a collector that reports one title twice reaches one
    # entity with two readings, and both counts have to say so.
    resolved_rows = 0
    # Rows that reach no sensor and should not. Counted apart so the report
    # says why ``resolved`` and the unresolved lists do not add up to the
    # number of rows the collector sent.
    attribute_rows = 0
    setting_rows = 0
    unresolved_rows = 0

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
            resolved_rows += 1
        elif is_attribute_reading(title):
            attribute_rows += 1
            continue
        elif is_setting_reading(devcode, title):
            setting_rows += 1
            continue
        elif unit:
            unresolved_rows += 1
            unresolved_with_unit.append({"title": title, "unit": unit, "sample": value})
        else:
            unresolved_rows += 1
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
            "status": classify_support(devcode, unresolved_with_unit),
            "profile": profile["name"],
            "known_inverters": profile["known_inverters"],
            "resolved": resolved_rows,
            # Rows, so that resolved + unresolved == total exactly, even where
            # a collector repeats a title and the lists below deduplicate it.
            "unresolved": unresolved_rows,
            "total": len(reading_rows) - attribute_rows - setting_rows,
            "excluded": {
                "attribute_readings": attribute_rows,
                "declared_settings": setting_rows,
            },
            "sensors": len(resolved_keys),
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


# How far two sources may disagree about one reading before the difference is
# a unit mistake rather than two measurements taken a moment apart. The
# legitimate pairs in the committed evidence differ by well under a percent
# (50.1 Hz against 50.2, 230.5 V against 230.3); the PI18 energy counter in
# #53 differed by exactly a thousand.
SCALE_DISAGREEMENT_RATIO = 100.0


def cross_source_readings(report: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Pair a device report's readings with its cloud parameters, by sensor key.

    A hybrid snapshot carries the local value in ``readings`` and the cloud's
    own figure for the same sensor in ``parameters``, so a device report holds
    two independent measurements of one reading. That pairing is the only
    evidence a unit mistake in a local driver leaves behind in a support file,
    and it is what shows the PI18 ``ET`` query answering 10104399 beside the
    cloud's 10104.399 kWh (#53).

    Only readings both sources carry, and both carry as numbers, are returned.
    """
    devcode = report.get("devcode")
    readings = _numeric_by_key(devcode, report.get("readings") or [], "title", "value")
    parameters = _numeric_by_key(
        devcode, report.get("parameters") or [], "name", "value"
    )
    return {
        key: (readings[key], parameters[key])
        for key in sorted(readings.keys() & parameters.keys())
    }


def scale_disagreements(
    report: dict[str, Any], *, ratio: float = SCALE_DISAGREEMENT_RATIO
) -> dict[str, tuple[float, float]]:
    """Return the paired readings whose two sources disagree about scale."""
    disagreements: dict[str, tuple[float, float]] = {}
    for key, (local, cloud) in cross_source_readings(report).items():
        larger, smaller = max(abs(local), abs(cloud)), min(abs(local), abs(cloud))
        if smaller and larger / smaller >= ratio:
            disagreements[key] = (local, cloud)
    return disagreements


def _numeric_by_key(
    devcode: Any, points: list[dict[str, Any]], title_field: str, value_field: str
) -> dict[str, float]:
    """Resolve each point to its sensor key, keeping only numeric values.

    The first value for a key wins, as it does on the sensor platform: a
    collector that reports one title twice reaches one entity.
    """
    resolved: dict[str, float] = {}
    for point in points:
        title = point.get(title_field)
        if not isinstance(title, str) or not title.strip():
            continue
        raw = point.get(value_field)
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError):
            continue
        key = resolved_key_for(devcode, {"title": title, "val": raw})
        if key and key not in resolved:
            resolved[key] = value
    return resolved


def device_support_status(
    devcode: Any, readings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return just the support block for one device's readings.

    The sensor and the Repairs evaluation both need this on every refresh and
    neither needs the rest of a report, so this builds no readings list and
    performs no hashing.
    """
    return build_support_report(devcode=devcode, readings=readings)["support"]


def classify_support(
    devcode: Any,
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


def _control_names(control_fields: Any) -> list[str]:
    """Return the control-field names a diagnostics download recorded.

    A download carries the device's control template beside its readings, and
    which unresolved titles are that device's own settings is the one judgement
    a reviewer has to make about a new devcode. The coverage tooling shows them
    so the answer comes from the file rather than from the reviewer guessing.
    """
    if not isinstance(control_fields, list):
        return []
    return [
        str(field["name"]).strip()
        for field in control_fields
        if isinstance(field, dict) and str(field.get("name") or "").strip()
    ]


def normalized_reports(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one comparable record per device, from either report shape.

    Evidence reaches the repository as a CLI analysis or, now, as a
    diagnostics download, and the coverage tooling and its test guard both
    (#60). Each record carries the devcode, the raw titles, the units observed
    for them, the names of its control fields when the shape records any, which
    path produced it, and whether its checksum still matches.

    A download is read as the reporter attaches it: Home Assistant writes the
    report a diagnostics hook returns under a ``data`` key, beside the host and
    integration metadata it adds itself, so the shapes below sit one level down
    in every file that reaches an issue (#62).
    """
    data = payload.get("data")
    if isinstance(data, dict) and ("devices" in data or "readings" in data):
        return normalized_reports(data)

    if "analysis" in payload and isinstance(payload["analysis"], dict):
        analysis = payload["analysis"]
        return [
            {
                "devcode": analysis.get("devcode"),
                "titles": [str(title) for title in analysis.get("sensor_titles", [])],
                "units": _units_from_analysis(analysis),
                "source": analysis.get("source", "cli_analysis"),
                "controls": [],
                "checksum": analysis.get("checksum"),
                "checksum_valid": bool(analysis.get("checksum"))
                and analysis["checksum"] == analysis_checksum(analysis),
            }
        ]

    devices = payload.get("devices")
    if isinstance(devices, list):
        return [
            record
            for device in devices
            if isinstance(device, dict)
            for record in normalized_reports(device)
        ]

    if "readings" in payload:
        readings = payload.get("readings") or []
        return [
            {
                "devcode": payload.get("devcode"),
                "titles": [str(reading.get("title", "")) for reading in readings],
                "units": {
                    str(reading.get("title")): str(reading.get("unit"))
                    for reading in readings
                    if reading.get("title") and reading.get("unit")
                },
                "source": payload.get("source", "integration_diagnostics"),
                "controls": _control_names(payload.get("control_fields")),
                "checksum": payload.get("checksum"),
                "checksum_valid": bool(payload.get("checksum"))
                and payload["checksum"] == report_checksum(payload),
            }
        ]

    raise ValueError("not a devcode analysis or support report")


def _units_from_analysis(analysis: dict[str, Any]) -> dict[str, str]:
    """Collect the units a CLI analysis observed, keyed by raw title.

    It records a unit for the sampled readings only, which is why a report
    built in Home Assistant is the better evidence.
    """
    units: dict[str, str] = {}
    for section, label in (("sample_data", "title"), ("parameters", "name")):
        for point in analysis.get(section, []):
            title = point.get(label)
            unit = (point.get("unit") or "").strip()
            if title and unit:
                units[str(title)] = unit
    return units
