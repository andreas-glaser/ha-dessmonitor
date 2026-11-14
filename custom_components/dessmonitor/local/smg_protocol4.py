"""Read-only register layouts for the vendor's protocol numbers 3 and 4.

Reference: "Modbus_RTU Communication Description", version 1.0, November 2024,
distributed as ``Communication.Protocol.No.3-10.docx`` and published with an
ESPHome configuration for an ANENJI 11 kW:
https://github.com/PreK/esphome-anenji-11kw-native-modbus/tree/
55a330585846d57b4f24e6467201d8dde8985ee7

The filename names a range the document does not: its own scope section covers
protocol numbers **3, 4, 5 and 6**, and says nothing about 7 to 10. Protocols 3
and 4 share one layout - same addresses, same scaling, same meanings - and
differ only in which registers exist:

- ``252..256`` (the totalled output) and ``384..388`` (the second output) are
  protocol 4 only. On protocol 3 the same measurements are read per phase at
  ``347..350``, which both protocols carry.
- ``302..304`` (the PV aggregates) and ``389..391`` (the second string) are
  protocols 3 and 4, and absent on 5 and 6.

The document warns that a read must span whole blocks, so each layout names its
own block list rather than reading the union and ignoring what does not apply.

Protocol 4's addresses and scaling were checked against two hardware read
cycles on an ANJ-11KW-48V-W-P. Protocol 3's were measured on a Maxsky EM11000
(#76) for the pack, the AC output and both strings, against the vendor app's
own figures at the same minute; the rest of its fields are the document's.

Do not use the standard SMG ``201..234`` field positions for either layout.
That map is a different vendor document describing a different generation, and
over these addresses it means something else entirely: it reads 202 as the grid
voltage where this one has the total mains current, and 227 as a temperature
where this one has the inverter frequency. Reading one with the other's map
yields plausible-looking numbers rather than a decode failure, which is why a
route is only ever kept when the map it was read with decodes.
"""

from __future__ import annotations

from typing import Any

from .modbus import ModbusError, to_signed_16

PROTOCOL4_CLOUD_DEVICE_CODE = 6544

PROTOCOL4_BLOCKS = (
    (201, 7),
    (227, 5),
    (252, 5),
    (277, 5),
    (302, 4),
    (338, 16),
    (384, 8),
    (702, 3),
)

# Protocol 3 has neither the totalled output block nor the second output, and
# reads 389..391 on its own rather than as the tail of 384..391.
PROTOCOL3_BLOCKS = (
    (201, 7),
    (227, 5),
    (277, 5),
    (302, 4),
    (338, 16),
    (389, 3),
    (702, 3),
)

# Reuse existing sensor titles (including SOC) to keep cloud entity identities.
# Reserved fields are deliberately absent. 606/607 are setpoints, not readings.
_COMMON_FIELDS = (
    (203, "Grid Frequency", 100),
    (206, "AC charging power", 1),
    (227, "Inverter frequency", 100),
    (231, "INV Module Termperature", 1),
    (277, "Battery Voltage", 10),
    (278, "Battery Current", 10),
    (279, "Battery Power", 1),
    (281, "DC Module Termperature", 1),
    (302, "PV Power", 1),
    (303, "PV Total Charger Power", 1),
    (304, "PV charging current", 10),
    (305, "PV Temperature", 1),
    (338, "Grid Voltage", 10),
    (340, "Grid Power", 1),
    (342, "Inverter Voltage", 10),
    (343, "Inverter Current", 10),
    (346, "Output Voltage", 10),
    (351, "PV1 Voltage", 10),
    (352, "PV1 Charger Current", 10),
    (353, "PV1 Charger Power", 1),
    (389, "PV2 Voltage", 10),
    (390, "PV2 Charger Current", 10),
    (391, "PV2 Charger Power", 1),
)

# The totalled output, which only protocol 4 reports.
_PROTOCOL4_FIELDS = _COMMON_FIELDS + (
    (252, "Output Current", 10),
    (253, "Output Frequency", 100),
    (254, "Output Active Power", 1),
    (255, "Output Apparent Power", 1),
    (256, "Load Percent", 1),
    (384, "Second Output Voltage", 10),
)

# The same measurements on protocol 3, read for the one output it has. The
# output frequency at 253 is left out: the document declares the register for
# this protocol but puts it inside a block whose other four registers are
# protocol 4's, and it warns that a read spanning part of a block answers with
# zeros rather than an error. In hybrid mode the cloud carries that reading.
_PROTOCOL3_FIELDS = _COMMON_FIELDS + (
    (347, "Output Current", 10),
    (348, "Output Active Power", 1),
    (349, "Output Apparent Power", 1),
    (350, "Load Percent", 1),
)

_MODES = {
    0: "Power On",
    1: "Standby",
    2: "Grid Mode",
    3: "Off-grid Mode",
    4: "Grid Mode",
    5: "Charging",
    6: "Fault",
}


def decode_protocol4(registers: dict[int, int]) -> dict[str, Any]:
    """Decode one complete protocol-4 snapshot."""
    return _decode(registers, PROTOCOL4_BLOCKS, _PROTOCOL4_FIELDS, "protocol 4")


def decode_protocol3(registers: dict[int, int]) -> dict[str, Any]:
    """Decode one complete protocol-3 snapshot."""
    return _decode(registers, PROTOCOL3_BLOCKS, _PROTOCOL3_FIELDS, "protocol 3")


def _decode(
    registers: dict[int, int],
    blocks: tuple[tuple[int, int], ...],
    fields: tuple[tuple[int, str, int], ...],
    layout: str,
) -> dict[str, Any]:
    """Decode one complete snapshot; a partial cycle must not look fresh."""
    expected = {
        address for start, count in blocks for address in range(start, start + count)
    }
    if not expected.issubset(registers):
        raise ModbusError(f"{layout} snapshot is incomplete")
    if any(
        type(registers[address]) is not int or not 0 <= registers[address] <= 65535
        for address in expected
    ):
        raise ModbusError(f"{layout} contains an invalid register value")
    mode = registers[201]
    soc = registers[280]
    if mode not in _MODES or not 0 <= soc <= 100:
        raise ModbusError(f"{layout} mode or SOC is invalid")

    values: dict[str, Any] = {"Operating mode": _MODES[mode], "SOC": soc}
    for address, title, divisor in fields:
        raw = to_signed_16(registers[address])
        values[title] = raw if divisor == 1 else round(raw / divisor, 2)
    # Keep legitimate zero readings, but reject an entirely unpowered/empty map.
    if not any(
        0 < values[title] < maximum
        for title, maximum in (
            ("Battery Voltage", 1000),
            ("Grid Voltage", 300),
            ("Output Voltage", 300),
        )
    ):
        raise ModbusError(f"{layout} snapshot has no plausible voltage")
    for title in ("Grid Frequency", "Output Frequency", "Inverter frequency"):
        if title in values and not 0 <= values[title] <= 70:
            raise ModbusError(f"{layout} frequency is invalid")
    values["Battery Charging Current"] = max(0, values["Battery Current"])
    values["Battery Discharge Current"] = max(0, -values["Battery Current"])
    values["Energy Today"] = registers[702] / 100
    values["Energy Total"] = ((registers[703] << 16) | registers[704]) / 100
    return values
