"""P17 and PI18 profiles with normalized DessMonitor sensor mapping.

This profile deliberately exposes only fields whose position and scale are
known for each protocol ID. Unknown fields remain unavailable instead of
being published with a plausible but potentially wrong label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .protocol import P17Response, ProtocolError, parse_p17_response


@dataclass(frozen=True, slots=True)
class Field:
    """One normalized value in a comma-separated inverter response."""

    title: str
    index: int
    unit: str
    scale: float = 1.0


GS_FIELDS = (
    Field("Grid Voltage", 0, "V", 0.1),
    Field("Grid Frequency", 1, "Hz", 0.1),
    Field("Output Voltage", 2, "V", 0.1),
    Field("Output Frequency", 3, "Hz", 0.1),
    Field("Output Apparent Power", 4, "VA"),
    Field("Output Active Power", 5, "W"),
    Field("Load Percent", 6, "%"),
    Field("Battery Voltage", 7, "V", 0.1),
    Field("Battery Charging Current", 9, "A"),
    Field("Battery Discharge Current", 10, "A"),
    Field("State of Charge", 12, "%"),
    Field("Inverter Heat Sink Temperature", 13, "°C"),
    Field("PV1 Charger Power", 16, "W"),
    Field("PV1 Voltage", 18, "V", 0.1),
    Field("PV2 Charger Power", 19, "W"),
)

GS2_FIELDS = (
    Field("PV2 Voltage", 1, "V", 0.1),
    Field("PV2 Charger Power", 2, "W"),
)

PI18_GS_FIELDS = (
    Field("Grid Voltage", 0, "V", 0.1),
    Field("Grid Frequency", 1, "Hz", 0.1),
    Field("Output Voltage", 2, "V", 0.1),
    Field("Output Frequency", 3, "Hz", 0.1),
    Field("Output Apparent Power", 4, "VA"),
    Field("Output Active Power", 5, "W"),
    Field("Load Percent", 6, "%"),
    Field("Battery Voltage", 7, "V", 0.1),
    Field("Battery Discharge Current", 10, "A"),
    Field("Battery Charging Current", 11, "A"),
    Field("State of Charge", 12, "%"),
    Field("Inverter Heat Sink Temperature", 13, "°C"),
    Field("PV1 Charger Power", 16, "W"),
    Field("PV2 Charger Power", 17, "W"),
    Field("PV1 Voltage", 18, "V", 0.1),
    Field("PV2 Voltage", 19, "V", 0.1),
)

SENSOR_UNITS = {
    field.title: field.unit for field in (*GS_FIELDS, *GS2_FIELDS, *PI18_GS_FIELDS)
} | {"Operating mode": "", "Energy Total": "kWh"}

MODE_MAP = {
    "00": "Power On",
    "01": "Standby",
    "02": "Line",
    "03": "Battery",
    "04": "Fault",
    "05": "Hybrid Mode",
    "06": "Shutdown Approaching",
    "P": "Power On",
    "S": "Standby",
    "L": "Line",
    "B": "Battery",
    "F": "Fault",
    "H": "Power Saving",
    "D": "Shutdown Approaching",
}


def parse_command_response(
    command: str, frame: bytes, *, protocol_id: str = "17"
) -> dict[str, Any]:
    """Validate an inverter frame and parse one supported command."""
    if protocol_id not in {"17", "18"}:
        raise ProtocolError(
            "unsupported inverter protocol", reason="unsupported_protocol"
        )
    response = parse_p17_response(frame, escape_crc=protocol_id != "18")
    if response.response_type == "N":
        raise CommandNotSupported(command)
    if response.response_type != "D":
        raise ProtocolError(f"{command} returned an unexpected acknowledgement")

    if command == "GS":
        if protocol_id == "18":
            return _parse_fields(response, PI18_GS_FIELDS, minimum_fields=28)
        return _parse_fields(response, GS_FIELDS, minimum_fields=20)
    if command == "GS2" and protocol_id == "17":
        return _parse_fields(response, GS2_FIELDS, minimum_fields=3)
    if command == "MOD":
        mode = response.data.strip()
        return {"Operating mode": MODE_MAP.get(mode, "Unknown")}
    if command == "ET":
        return {"Energy Total": _parse_number(response.data, 1.0)}
    if command == "PI":
        identified = response.data.strip()
        if identified not in {"17", "18"}:
            raise ProtocolError(
                "unsupported inverter protocol", reason="unsupported_protocol"
            )
        return {"PI": identified}
    if command in {"ID", "VFW"} or (command == "GMN" and protocol_id == "17"):
        return {
            command: _decode_string(response.data, command, protocol_id=protocol_id)
        }
    if command == "PIRI":
        return _parse_rating_info(response)
    raise CommandNotSupported(command)


def _parse_fields(
    response: P17Response,
    fields: tuple[Field, ...],
    *,
    minimum_fields: int,
) -> dict[str, Any]:
    """Parse verified field positions without guessing missing values."""
    values = [value.strip() for value in response.data.split(",")]
    if len(values) < minimum_fields:
        raise ProtocolError(
            f"status response has {len(values)} fields; expected at least {minimum_fields}"
        )
    result: dict[str, Any] = {}
    for field in fields:
        raw = values[field.index]
        if raw:
            result[field.title] = _parse_number(raw, field.scale)
    return result


def _parse_number(value: str, scale: float) -> int | float:
    """Parse a finite decimal integer and apply a known scale."""
    try:
        parsed = int(value.strip(), 10)
    except ValueError as err:
        raise ProtocolError(f"expected an integer value, received {value!r}") from err
    try:
        scaled = parsed * scale
    except OverflowError as err:
        raise ProtocolError("numeric value is outside the supported range") from err
    if scale == 1.0:
        return parsed
    return round(scaled, 3)


def _decode_string(value: str, command: str, *, protocol_id: str) -> str:
    """Decode identity padding while preserving PI18's three CPU versions."""
    raw = value.strip()
    length_prefixed = command == "ID" or protocol_id == "17"
    if length_prefixed and len(raw) >= 3:
        try:
            length = int(raw[:2])
        except ValueError:
            length = 0
        if 0 < length <= len(raw) - 2:
            raw = raw[2 : 2 + length]
        else:
            raw = raw.rstrip("0") or raw
    if not raw or len(raw) > 128:
        raise ProtocolError(f"{command} returned an invalid string")
    return raw


def _parse_rating_info(response: P17Response) -> dict[str, Any]:
    """Extract device ratings used as metadata, not control values."""
    values = [value.strip() for value in response.data.split(",")]
    if len(values) < 8:
        raise ProtocolError("rating response is missing required fields")
    return {
        "rated_output_power": _parse_number(values[6], 1.0),
        "rated_battery_voltage": _parse_number(values[7], 0.1),
    }


class CommandNotSupported(ProtocolError):
    """Raised when an inverter explicitly NAKs a command."""
