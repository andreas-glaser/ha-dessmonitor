"""Writable PI18/P17 settings, read back from the inverter's own PIRI reply.

Same two rules as the PI30 table: a setting is declared only where ``PIRI``
reports its value, and a write is finished only when that value has moved.

Two of these commands write a pair of settings at once. ``MCHGV`` carries the
bulk and float voltages together and ``BUCD`` the re-charge and re-discharge
voltages, so changing one means sending the other unchanged. The partner's
value is taken from a ``PIRI`` reply read immediately before the write rather
than from the cached template, because a value edited on the inverter's own
panel since the last poll would otherwise be written back to what it used to
be.

Field indices are positions in the comma-separated ``PIRI`` reply and agree
between the ``pi18`` and ``pi18sv`` command tables published by the mpp-solar
project; indices 6 and 7 are already relied on by this integration's own
rating parse.
"""

from __future__ import annotations

from collections.abc import Mapping

from .settings import KIND_OPTIONS, KIND_VALUE, LocalSetting, SettingNotWritable

# These commands take a parallel-unit number, and a single inverter is unit
# zero in every published example (``MCHGC0,030``).
_PARALLEL_UNIT = 0

_BATTERY_CLASSES = (12.0, 24.0, 48.0)
_CLASS_TOLERANCE = 0.15
_BATTERY_RATING_INDEX = 7

MCHGCR = "MCHGCR"
MUCHGCR = "MUCHGCR"
ENUMERATION_QUERIES: tuple[str, ...] = (MCHGCR, MUCHGCR)

# Re-discharge accepts "the battery is full" as well as a voltage. It is
# declared as the voltage band plus that one discrete value, so the band is
# what the slider offers and a zero the inverter reports is still shown.
_FULL_BATTERY = 0.0


def _tenths(value: str) -> int:
    """Return a voltage in the tenths of a volt these commands carry."""
    return int(round(float(value) * 10))


def _digit(setting: LocalSetting, value: str, _r: Mapping[str, str]) -> str:
    """Encode a single-digit selection code."""
    return f"{setting.command}{int(value):d}"


def _unit_digit(setting: LocalSetting, value: str, _r: Mapping[str, str]) -> str:
    """Encode a unit-addressed selection code, such as ``PCP0,1``."""
    return f"{setting.command}{_PARALLEL_UNIT},{int(value):d}"


def _voltage(setting: LocalSetting, value: str, _r: Mapping[str, str]) -> str:
    """Encode a single three-digit voltage setpoint, such as ``PSDV450``."""
    return f"{setting.command}{_tenths(value):03d}"


def _unit_current(setting: LocalSetting, value: str, _r: Mapping[str, str]) -> str:
    """Encode a unit-addressed current limit, such as ``MCHGC0,030``."""
    return f"{setting.command}{_PARALLEL_UNIT},{int(value, 10):03d}"


def _charging_voltages(
    setting: LocalSetting, value: str, readback: Mapping[str, str]
) -> str:
    """Encode bulk and float together, changing only the named one."""
    bulk = (
        value
        if setting.key == "battery_bulk_voltage"
        else readback["battery_bulk_voltage"]
    )
    float_voltage = (
        value
        if setting.key == "battery_float_voltage"
        else readback["battery_float_voltage"]
    )
    if _tenths(float_voltage) > _tenths(bulk):
        # The inverter refuses this pairing, and saying so by name is more use
        # than an unexplained NAK from a command that carries both values.
        raise SettingNotWritable(
            f"the float voltage ({float_voltage} V) cannot be above the bulk "
            f"voltage ({bulk} V)"
        )
    return f"MCHGV{_tenths(bulk):03d},{_tenths(float_voltage):03d}"


def _utility_thresholds(
    setting: LocalSetting, value: str, readback: Mapping[str, str]
) -> str:
    """Encode the re-charge and re-discharge voltages together."""
    recharge = (
        value
        if setting.key == "battery_recharge_voltage"
        else readback["battery_recharge_voltage"]
    )
    redischarge = (
        value
        if setting.key == "battery_redischarge_voltage"
        else readback["battery_redischarge_voltage"]
    )
    return f"BUCD{_tenths(recharge):03d},{_tenths(redischarge):03d}"


def battery_class(rating_fields: tuple[str, ...]) -> float | None:
    """Return the nominal battery voltage PIRI reports, or None if unclear."""
    if len(rating_fields) <= _BATTERY_RATING_INDEX:
        return None
    try:
        reported = int(rating_fields[_BATTERY_RATING_INDEX], 10) / 10
    except ValueError:
        return None
    for nominal in _BATTERY_CLASSES:
        if abs(reported - nominal) <= nominal * _CLASS_TOLERANCE:
            return nominal
    return None


def settings_for(rating_fields: tuple[str, ...]) -> tuple[LocalSetting, ...]:
    """Return the settings this inverter reports, scaled to its battery class."""
    settings: list[LocalSetting] = [
        LocalSetting(
            key="output_source_priority",
            name="Output Source Priority",
            kind=KIND_OPTIONS,
            index=17,
            command="POP",
            encode=_digit,
            options={
                "0": "Solar → Utility → Battery",
                "1": "Solar → Battery → Utility",
            },
        ),
        LocalSetting(
            key="charger_source_priority",
            name="Charger Source Priority",
            kind=KIND_OPTIONS,
            index=18,
            command="PCP",
            encode=_unit_digit,
            options={
                "0": "Solar first",
                "1": "Solar and Utility",
                "2": "Only Solar",
            },
        ),
        LocalSetting(
            key="solar_power_priority",
            name="Solar Power Priority",
            kind=KIND_OPTIONS,
            index=23,
            command="PSP",
            encode=_digit,
            options={
                "0": "Battery → Load → Utility",
                "1": "Load → Battery → Utility",
            },
        ),
        LocalSetting(
            key="battery_type",
            name="Battery Type",
            kind=KIND_OPTIONS,
            index=13,
            command="PBT",
            encode=_digit,
            options={"0": "AGM", "1": "Flooded", "2": "User"},
        ),
        LocalSetting(
            key="max_charging_current",
            name="Max Charging Current",
            kind=KIND_OPTIONS,
            index=15,
            command="MCHGC",
            encode=_unit_current,
            unit="A",
            options_from=MCHGCR,
        ),
        LocalSetting(
            key="max_ac_charging_current",
            name="Max AC Charging Current",
            kind=KIND_OPTIONS,
            index=14,
            command="MUCHGC",
            encode=_unit_current,
            unit="A",
            options_from=MUCHGCR,
        ),
    ]

    nominal = battery_class(rating_fields)
    if nominal is None:
        return tuple(settings)
    ratio = nominal / 48.0
    settings.extend(
        (
            LocalSetting(
                key="battery_cutoff_voltage",
                name="Battery Cut-Off Voltage",
                kind=KIND_VALUE,
                index=10,
                command="PSDV",
                encode=_voltage,
                unit="V",
                scale=0.1,
                decimals=1,
                minimum=round(40.0 * ratio, 1),
                maximum=round(48.0 * ratio, 1),
            ),
            LocalSetting(
                key="battery_bulk_voltage",
                name="Battery Bulk Voltage",
                kind=KIND_VALUE,
                index=11,
                command="MCHGV",
                encode=_charging_voltages,
                unit="V",
                scale=0.1,
                decimals=1,
                minimum=round(48.0 * ratio, 1),
                maximum=round(58.5 * ratio, 1),
                writes_with=("battery_float_voltage",),
            ),
            LocalSetting(
                key="battery_float_voltage",
                name="Battery Float Voltage",
                kind=KIND_VALUE,
                index=12,
                command="MCHGV",
                encode=_charging_voltages,
                unit="V",
                scale=0.1,
                decimals=1,
                minimum=round(48.0 * ratio, 1),
                maximum=round(58.4 * ratio, 1),
                writes_with=("battery_bulk_voltage",),
            ),
            LocalSetting(
                key="battery_recharge_voltage",
                name="Battery Re-Charge Voltage",
                kind=KIND_VALUE,
                index=8,
                command="BUCD",
                encode=_utility_thresholds,
                unit="V",
                scale=0.1,
                decimals=1,
                minimum=round(44.0 * ratio, 1),
                maximum=round(51.0 * ratio, 1),
                writes_with=("battery_redischarge_voltage",),
            ),
            LocalSetting(
                key="battery_redischarge_voltage",
                name="Battery Re-Discharge Voltage",
                kind=KIND_VALUE,
                index=9,
                command="BUCD",
                encode=_utility_thresholds,
                unit="V",
                scale=0.1,
                decimals=1,
                minimum=round(48.0 * ratio, 1),
                maximum=round(58.0 * ratio, 1),
                extra_values=(_FULL_BATTERY,),
                writes_with=("battery_recharge_voltage",),
            ),
        )
    )
    return tuple(settings)


def parse_enumeration(command: str, data: str) -> tuple[str, ...]:
    """Decode a list of accepted current values from its own inquiry."""
    if command not in ENUMERATION_QUERIES:
        raise ValueError(f"{command} does not enumerate a setting's values")
    offered = tuple(
        value.strip() for value in data.split(",") if value.strip().isdigit()
    )
    if not offered:
        raise ValueError(f"{command} reported no values")
    return offered
