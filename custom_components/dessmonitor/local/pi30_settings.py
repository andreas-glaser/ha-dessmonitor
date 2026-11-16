"""Writable PI30 settings, read back from the inverter's own QPIRI reply.

Every entry here is a command the inverter answers ``(ACK`` to and a field
``QPIRI`` reports, so a write can be proven rather than assumed. Commands with
no QPIRI field, and commands two reputable sources describe differently, are
left out on purpose; ``docs/LOCAL_MODE.md`` names them and what evidence would
settle each one.

Field indices are the position in the space-separated ``QPIRI`` reply. They
agree between the ``pi30`` and ``pi30max`` command tables published by the
mpp-solar project, and the first eight are already relied on by this
integration's own rating parse.
"""

from __future__ import annotations

from collections.abc import Mapping

from .settings import KIND_OPTIONS, KIND_VALUE, LocalSetting, SettingNotWritable

# Parallel-unit number. These commands take one, and a single inverter is unit
# zero in every example the published tables carry (``MCHGC040`` is unit 0,
# 40 A). A parallel installation addresses its units over separate inverter
# addresses here, so each one is still unit zero on its own link.
_PARALLEL_UNIT = 0

# Battery nominal classes a 12 V multiple of the documented 48 V range applies
# to, and how far a reported rating may sit from one to be recognised as it.
_BATTERY_CLASSES = (12.0, 24.0, 48.0)
_CLASS_TOLERANCE = 0.15

# Index of the battery rating voltage in QPIRI, which decides the class above.
_BATTERY_RATING_INDEX = 7

# Allowed values for the utility charging current are enumerated by the
# inverter rather than fixed by the protocol.
QMUCHGCR = "QMUCHGCR"
ENUMERATION_QUERIES: tuple[str, ...] = (QMUCHGCR,)

# The field QPIRI reports each enumerated setting's current value in.
_MAX_AC_CHARGING_CURRENT_INDEX = 13


def _voltage(setting: LocalSetting, value: str, _readback: Mapping[str, str]) -> str:
    """Encode a PI30 voltage setpoint as ``nn.n``."""
    return f"{setting.command}{float(value):04.1f}"


def _code(setting: LocalSetting, value: str, _readback: Mapping[str, str]) -> str:
    """Encode a two-digit PI30 selection code."""
    return f"{setting.command}{int(value):02d}"


def _frequency(_setting: LocalSetting, value: str, _r: Mapping[str, str]) -> str:
    """Encode the output frequency, which takes no leading zero."""
    return f"F{int(float(value)):d}"


def _utility_current(
    setting: LocalSetting, value: str, _readback: Mapping[str, str]
) -> str:
    """Encode the utility charging limit as a unit digit and two current digits."""
    amps = int(value, 10)
    if not 0 <= amps <= 99:
        # Both published tables give this command two current digits. The
        # protocol notes say a limit above 99 A is sent as three digits for the
        # *total* charging current, and nothing says it is for this one, so a
        # guess here would write a different limit than the owner chose.
        raise SettingNotWritable(
            f"{setting.name} cannot be set to {amps} A over the local link: this "
            "command carries two current digits and no published table shows "
            "the form a higher limit takes"
        )
    return f"{setting.command}{_PARALLEL_UNIT}{amps:02d}"


def battery_class(rating_fields: tuple[str, ...]) -> float | None:
    """Return the nominal battery voltage QPIRI reports, or None if unclear.

    The documented setpoint ranges are given for a 48 V unit, and the two the
    tables also give for 24 V and 12 V units are exactly that range halved and
    quartered (44-51 V becomes 22-25.5 V and 11-12.8 V). The ratio is applied
    to the other setpoints on that evidence. A rating that matches no class is
    not scaled by a guess: the voltage settings are simply not offered.
    """
    if len(rating_fields) <= _BATTERY_RATING_INDEX:
        return None
    try:
        reported = float(rating_fields[_BATTERY_RATING_INDEX])
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
            index=16,
            command="POP",
            encode=_code,
            options={
                "0": "Utility first",
                "1": "Solar first",
                "2": "Solar → Battery → Utility",
            },
        ),
        LocalSetting(
            key="charger_source_priority",
            name="Charger Source Priority",
            kind=KIND_OPTIONS,
            index=17,
            command="PCP",
            encode=_code,
            options={
                "0": "Utility first",
                "1": "Solar first",
                "2": "Solar and Utility",
                "3": "Only Solar",
            },
        ),
        LocalSetting(
            key="battery_type",
            name="Battery Type",
            kind=KIND_OPTIONS,
            index=12,
            command="PBT",
            encode=_code,
            # The reply reports further codes, for Pylontech and other packs,
            # that the setter does not accept. A reported code outside these
            # three leaves the setting unreported rather than offering an
            # owner on a lithium pack a choice of three that are not it.
            options={"0": "AGM", "1": "Flooded", "2": "User"},
        ),
        LocalSetting(
            key="grid_working_range",
            name="AC Input Range",
            kind=KIND_OPTIONS,
            index=15,
            command="PGR",
            encode=_code,
            options={"0": "Appliance", "1": "UPS"},
        ),
        LocalSetting(
            key="output_frequency",
            # Not "Output Frequency": that is the live reading's title, and a
            # control sharing a reading's name reads the measurement instead
            # of the setpoint (#61). This is the spelling devcodes 2449 and
            # 2451 already use for the same setting.
            name="AC Output Rating Frequency",
            kind=KIND_OPTIONS,
            index=3,
            command="F",
            encode=_frequency,
            unit="Hz",
            options={"50": "50 Hz", "60": "60 Hz"},
        ),
        LocalSetting(
            key="max_ac_charging_current",
            name="Max AC Charging Current",
            kind=KIND_OPTIONS,
            index=_MAX_AC_CHARGING_CURRENT_INDEX,
            command="MUCHGC",
            encode=_utility_current,
            unit="A",
            options_from=QMUCHGCR,
            maximum=99,
        ),
    ]

    nominal = battery_class(rating_fields)
    if nominal is not None:
        ratio = nominal / 48.0
        for key, name, index, command, low, high in (
            (
                "battery_recharge_voltage",
                "Battery Re-Charge Voltage",
                8,
                "PBCV",
                44.0,
                51.0,
            ),
            (
                "battery_redischarge_voltage",
                "Battery Re-Discharge Voltage",
                22,
                "PBDV",
                48.0,
                58.0,
            ),
            (
                "battery_cutoff_voltage",
                "Battery Cut-Off Voltage",
                9,
                "PSDV",
                40.0,
                48.0,
            ),
            ("battery_bulk_voltage", "Battery Bulk Voltage", 10, "PCVV", 48.0, 58.4),
            ("battery_float_voltage", "Battery Float Voltage", 11, "PBFT", 48.0, 58.4),
        ):
            settings.append(
                LocalSetting(
                    key=key,
                    name=name,
                    kind=KIND_VALUE,
                    index=index,
                    command=command,
                    encode=_voltage,
                    unit="V",
                    decimals=1,
                    minimum=round(low * ratio, 1),
                    maximum=round(high * ratio, 1),
                )
            )
    return tuple(settings)


def parse_enumeration(command: str, data: str) -> tuple[str, ...]:
    """Decode a list of accepted current values from its own inquiry."""
    if command != QMUCHGCR:
        raise ValueError(f"{command} does not enumerate a setting's values")
    offered = tuple(value for value in data.split() if value.isdigit())
    if not offered:
        raise ValueError(f"{command} reported no values")
    return offered
