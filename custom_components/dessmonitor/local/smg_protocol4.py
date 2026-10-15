"""Read-only protocol-number 4 register layout, verified on ANJ-11KW-48V-W-P.

Reference: Communication.Protocol.No.3-10.docx, register 184 == 4.
https://github.com/PreK/esphome-anenji-11kw-native-modbus/tree/
55a330585846d57b4f24e6467201d8dde8985ee7

Register addresses and scaling were checked against two hardware read cycles.
Do not use the standard SMG 201..234 field positions for this layout.
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

# Reuse existing sensor titles (including SOC) to keep cloud entity identities.
# Reserved fields are deliberately absent. 606/607 are setpoints, not readings.
_FIELDS = (
    (203, "Grid Frequency", 100),
    (206, "AC charging power", 1),
    (227, "Inverter frequency", 100),
    (231, "INV Module Termperature", 1),
    (252, "Output Current", 10),
    (253, "Output Frequency", 100),
    (254, "Output Active Power", 1),
    (255, "Output Apparent Power", 1),
    (256, "Load Percent", 1),
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
    (384, "Second Output Voltage", 10),
    (389, "PV2 Voltage", 10),
    (390, "PV2 Charger Current", 10),
    (391, "PV2 Charger Power", 1),
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
    """Decode one complete snapshot; a partial cycle must not look fresh."""
    expected = {
        address
        for start, count in PROTOCOL4_BLOCKS
        for address in range(start, start + count)
    }
    if not expected.issubset(registers):
        raise ModbusError("protocol 4 snapshot is incomplete")
    if any(
        type(registers[address]) is not int or not 0 <= registers[address] <= 65535
        for address in expected
    ):
        raise ModbusError("protocol 4 contains an invalid register value")
    mode = registers[201]
    soc = registers[280]
    if mode not in _MODES or not 0 <= soc <= 100:
        raise ModbusError("protocol 4 mode or SOC is invalid")

    values: dict[str, Any] = {"Operating mode": _MODES[mode], "SOC": soc}
    for address, title, divisor in _FIELDS:
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
        raise ModbusError("protocol 4 snapshot has no plausible voltage")
    for title in ("Grid Frequency", "Output Frequency", "Inverter frequency"):
        if not 0 <= values[title] <= 70:
            raise ModbusError("protocol 4 frequency is invalid")
    values["Battery Charging Current"] = max(0, values["Battery Current"])
    values["Battery Discharge Current"] = max(0, -values["Battery Current"])
    values["Energy Today"] = registers[702] / 100
    values["Energy Total"] = ((registers[703] << 16) | registers[704]) / 100
    return values
