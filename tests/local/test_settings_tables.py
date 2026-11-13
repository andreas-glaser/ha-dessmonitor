"""The contract every declared local setting has to keep.

A write reaches someone's inverter, so these hold the two rules the tables rest
on: a setting is declared only where the inverter reports its value, and the
command that writes it is one the transport will carry. Anything a reviewer
would otherwise have to check by eye across two protocol tables is checked
here instead.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.local import p17_settings, pi30_settings
from custom_components.dessmonitor.local.pi30 import _STATUS_FIELDS
from custom_components.dessmonitor.local.profile import SENSOR_UNITS
from custom_components.dessmonitor.local.protocol import (
    P17_SETTER_COMMANDS,
    PI30_SETTER_COMMANDS,
    ProtocolError,
    build_p17_setter,
    build_pi30_setter,
)
from custom_components.dessmonitor.local.settings import (
    KIND_OPTIONS,
    KIND_VALUE,
    SettingNotWritable,
)

# One 48 V inverter's own reply on each protocol, in the published field order.
PI30_RATINGS = (
    "230.0 21.7 230.0 50.0 21.7 5000 4000 48.0 46.0 42.0 56.4 54.0 0 10 010 "
    "1 0 0 6 01 0 0 54.0 0 1"
).split(" ")
PI18_RATINGS = (
    "2300,217,2300,500,217,5000,5000,480,500,540,450,552,545,2,10,060,1,1,1,"
    "9,1,0,0,0,1,00"
).split(",")

PI30_ENUMERATIONS = {"QMUCHGCR": ("002", "010", "020", "030")}
PI18_ENUMERATIONS = {
    "MCHGCR": ("010", "020", "030", "040", "050", "060", "070", "080"),
    "MUCHGCR": ("002", "010", "020", "030"),
}

PROTOCOLS = (
    pytest.param(
        pi30_settings,
        tuple(PI30_RATINGS),
        PI30_ENUMERATIONS,
        PI30_SETTER_COMMANDS,
        build_pi30_setter,
        id="pi30",
    ),
    pytest.param(
        p17_settings,
        tuple(PI18_RATINGS),
        PI18_ENUMERATIONS,
        P17_SETTER_COMMANDS,
        build_p17_setter,
        id="pi18",
    ),
)


def _readback(tables, ratings, enumerations) -> dict[str, str]:
    """Decode every setting the way the backend decodes it."""
    return {
        setting.key: decoded
        for setting in tables.settings_for(ratings)
        if (decoded := setting.decode(ratings[setting.index], enumerations)) is not None
    }


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_every_command_is_one_the_transport_will_carry(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """A setter the frame builders do not declare cannot reach an inverter.

    The builders accept only the command names listed in ``protocol.py``, so a
    setting naming anything else would raise at the moment someone used it
    rather than when it was declared.
    """
    for setting in tables.settings_for(ratings):
        assert setting.command in allowed, setting.key


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_every_setting_could_be_verified_after_a_write(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """Each declaration names the field its value is read back from.

    This is the rule that makes a local write provable: without a read-back
    field there is no way to tell an owner the setting moved, so the
    declaration itself is refused.
    """
    for setting in tables.settings_for(ratings):
        assert setting.index >= 0, setting.key
        assert setting.index < len(ratings), setting.key
        if setting.kind == KIND_VALUE:
            assert setting.minimum is not None and setting.maximum is not None
            assert setting.minimum < setting.maximum
        else:
            assert setting.options or setting.options_from, setting.key


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_no_two_settings_share_a_name_or_a_key(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """Two controls under one display name is the defect class from #58."""
    settings = tables.settings_for(ratings)
    assert len({setting.key for setting in settings}) == len(settings)
    assert len({setting.name for setting in settings}) == len(settings)


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_no_setting_is_named_after_a_live_reading(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """A control named like a reading shows the measurement, not the setpoint.

    Devcode 2376 answers the Output Voltage control with 229.8 V while the
    setpoint sits elsewhere (#61), and the entity then reports a setting the
    inverter does not have. A local control reads its value from the same
    payload the local readings are published in, so sharing a title with one
    of them would reproduce that exactly. This is why the frequency setpoint
    is called "AC Output Rating Frequency".
    """
    readings = {title.strip().casefold() for title in SENSOR_UNITS} | {
        title.strip().casefold() for title, _ in _STATUS_FIELDS
    }
    for setting in tables.settings_for(ratings):
        assert setting.name.strip().casefold() not in readings, setting.name


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_every_accepted_value_encodes_into_a_frame(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """Both ends of every range, and every option, build a valid setter.

    An encoder that produces a malformed argument would be found by an owner
    moving a slider to its end, not by a reviewer reading the format string.
    """
    readback = _readback(tables, ratings, enumerations)
    for setting in tables.settings_for(ratings):
        if setting.kind == KIND_OPTIONS:
            candidates = list(setting.options_in(enumerations))
        else:
            assert setting.minimum is not None and setting.maximum is not None
            middle = round((setting.minimum + setting.maximum) / 2, 1)
            candidates = [
                f"{value:.1f}"
                for value in (setting.minimum, middle, setting.maximum)
            ]
            candidates += [f"{extra:.1f}" for extra in setting.extra_values]
        assert candidates, setting.key
        for candidate in candidates:
            # A setpoint written together with a partner is exercised with the
            # partner at the same value. The pairing rules between them are
            # tested on their own; this is about the argument each encoder
            # produces at both ends of its range.
            paired = dict(readback) | {
                partner: candidate for partner in setting.writes_with
            }
            text = setting.command_for(candidate, paired, enumerations)
            assert text.startswith(setting.command)
            built = frame(text)
            assert built.endswith(b"\r")


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_a_value_outside_the_range_is_refused_before_it_is_sent(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """The inverter is not the first line of defence against a bad value."""
    readback = _readback(tables, ratings, enumerations)
    for setting in tables.settings_for(ratings):
        if setting.kind != KIND_VALUE:
            continue
        assert setting.maximum is not None
        with pytest.raises(SettingNotWritable):
            setting.command_for(f"{setting.maximum + 1:.1f}", readback, enumerations)


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_an_option_the_inverter_does_not_offer_is_refused(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """Only the codes this protocol documents, and the limits this unit listed."""
    readback = _readback(tables, ratings, enumerations)
    for setting in tables.settings_for(ratings):
        if setting.kind != KIND_OPTIONS:
            continue
        with pytest.raises(SettingNotWritable):
            setting.command_for("not-an-option", readback, enumerations)


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_a_field_outside_its_range_is_not_published_as_the_setting(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """A field order that does not match leaves the setting unreported.

    Both protocols are read positionally, so a firmware that moves a field
    would otherwise publish whatever sits at that index and write the owner's
    value back to it. A value the documented range cannot contain is treated
    as evidence that the index is not this setting.
    """
    for setting in tables.settings_for(ratings):
        if setting.kind != KIND_VALUE:
            continue
        assert setting.maximum is not None
        impossible = str(int((setting.maximum + 50) / (setting.scale or 1)))
        assert setting.decode(impossible, enumerations) is None, setting.key


@pytest.mark.parametrize(("tables", "ratings", "enumerations", "allowed", "frame"), PROTOCOLS)
def test_a_reported_setting_round_trips_through_its_own_command(
    tables, ratings, enumerations, allowed, frame
) -> None:
    """Writing back what the inverter reported produces a frame, not an error.

    This is the case a verification re-read exercises, and the one an owner
    hits by opening a control and saving it unchanged.
    """
    readback = _readback(tables, ratings, enumerations)
    for setting in tables.settings_for(ratings):
        current = readback.get(setting.key)
        if current is None:
            continue
        frame(setting.command_for(current, readback, enumerations))


def test_pi30_voltage_ranges_scale_to_the_reported_battery_class() -> None:
    """The 24 V and 12 V ranges are the documented ones, not an interpolation.

    The published tables give every setpoint range for a 48 V unit, and give
    24 V and 12 V ranges for two of them. Those two are exactly the 48 V range
    halved and quartered, which is the evidence the ratio is applied to the
    rest on. If this ever fails, the ratio is wrong and the other setpoints
    cannot be trusted either.
    """
    documented = {
        24.0: {"battery_recharge_voltage": (22.0, 25.5), "battery_redischarge_voltage": (24.0, 29.0)},
        12.0: {"battery_recharge_voltage": (11.0, 12.8), "battery_redischarge_voltage": (12.0, 14.5)},
    }
    for nominal, expected in documented.items():
        ratings = list(PI30_RATINGS)
        ratings[7] = f"{nominal:.1f}"
        by_key = {
            setting.key: setting for setting in pi30_settings.settings_for(tuple(ratings))
        }
        for key, (low, high) in expected.items():
            assert (by_key[key].minimum, by_key[key].maximum) == (low, high), key


def test_pi18_voltage_ranges_scale_the_same_way() -> None:
    """PI18 carries the same setpoints in tenths of a volt."""
    ratings = list(PI18_RATINGS)
    ratings[7] = "240"
    by_key = {setting.key: setting for setting in p17_settings.settings_for(tuple(ratings))}
    assert (by_key["battery_recharge_voltage"].minimum, by_key["battery_recharge_voltage"].maximum) == (22.0, 25.5)
    assert by_key["battery_cutoff_voltage"].maximum == 24.0


@pytest.mark.parametrize(
    ("tables", "ratings", "index", "unrecognised"),
    [
        (pi30_settings, PI30_RATINGS, 7, "96.0"),
        (p17_settings, PI18_RATINGS, 7, "960"),
    ],
)
def test_an_unrecognised_battery_rating_offers_no_voltage_setpoint(
    tables, ratings, index, unrecognised
) -> None:
    """A rating that matches no class is not scaled by a guess.

    Hardware outside 12, 24 and 48 V exists, and a setpoint range divided by a
    rating nobody documented would offer an owner voltages their inverter
    refuses - or worse, accepts. The selections stay; only the voltages go.
    """
    fields = list(ratings)
    fields[index] = unrecognised
    settings = tables.settings_for(tuple(fields))
    assert tables.battery_class(tuple(fields)) is None
    assert not [setting for setting in settings if setting.kind == KIND_VALUE]
    assert [setting for setting in settings if setting.kind == KIND_OPTIONS]


def test_pi18_charging_voltages_are_written_as_one_command() -> None:
    """Bulk and float share a command, so one write carries both values."""
    settings = {
        setting.key: setting for setting in p17_settings.settings_for(tuple(PI18_RATINGS))
    }
    readback = _readback(p17_settings, tuple(PI18_RATINGS), PI18_ENUMERATIONS)
    assert settings["battery_bulk_voltage"].writes_with == ("battery_float_voltage",)
    assert settings["battery_float_voltage"].writes_with == ("battery_bulk_voltage",)
    # 55.2 bulk and 54.5 float are what this inverter reported; changing the
    # bulk voltage must leave the float voltage exactly where it was.
    assert (
        settings["battery_bulk_voltage"].command_for("56.0", readback, PI18_ENUMERATIONS)
        == "MCHGV560,545"
    )
    assert (
        settings["battery_float_voltage"].command_for("54.0", readback, PI18_ENUMERATIONS)
        == "MCHGV552,540"
    )


def test_pi18_refuses_a_float_voltage_above_the_bulk_voltage() -> None:
    """The pairing the inverter rejects is named rather than sent blind."""
    settings = {
        setting.key: setting for setting in p17_settings.settings_for(tuple(PI18_RATINGS))
    }
    readback = _readback(p17_settings, tuple(PI18_RATINGS), PI18_ENUMERATIONS)
    with pytest.raises(SettingNotWritable, match="cannot be above the bulk"):
        settings["battery_float_voltage"].command_for("58.0", readback, PI18_ENUMERATIONS)


def test_a_composite_write_is_refused_while_its_partner_is_unknown() -> None:
    """Without the partner's value the command would change a second setting."""
    settings = {
        setting.key: setting for setting in p17_settings.settings_for(tuple(PI18_RATINGS))
    }
    with pytest.raises(SettingNotWritable, match="has not reported"):
        settings["battery_bulk_voltage"].command_for("56.0", {}, PI18_ENUMERATIONS)


def test_the_full_battery_redischarge_value_survives_its_own_range() -> None:
    """Zero means "until the battery is full" and is not in the voltage band.

    A slider cannot show a gap, so the band is published and the one discrete
    value is accepted beside it. A voltage between the two is refused.
    """
    setting = {
        item.key: item for item in p17_settings.settings_for(tuple(PI18_RATINGS))
    }["battery_redischarge_voltage"]
    readback = _readback(p17_settings, tuple(PI18_RATINGS), PI18_ENUMERATIONS)
    assert setting.hint == "48.0~58.0V"
    assert setting.decode("000") == "0.0"
    assert setting.command_for("0", readback, PI18_ENUMERATIONS) == "BUCD500,000"
    with pytest.raises(SettingNotWritable):
        setting.command_for("20.0", readback, PI18_ENUMERATIONS)


def test_a_charging_limit_the_command_cannot_express_is_not_offered() -> None:
    """PI30 carries two current digits, so a listed 120 A is left out.

    Both published tables give this command a unit digit and two current
    digits. The protocol notes say a limit above 99 A is sent as three digits
    for the *total* charging current, and nothing says it is for this one, so
    the value is dropped from the list rather than guessed at.
    """
    setting = {
        item.key: item for item in pi30_settings.settings_for(tuple(PI30_RATINGS))
    }["max_ac_charging_current"]
    offered = setting.options_in({"QMUCHGCR": ("002", "090", "100", "120")})
    assert list(offered) == ["002", "090"]
    assert offered["002"] == "2 A"
    with pytest.raises(SettingNotWritable):
        setting.command_for("120", {}, {"QMUCHGCR": ("002", "090", "100", "120")})


def test_an_enumerated_setting_is_unavailable_until_the_inverter_lists_it() -> None:
    """No list, no control: the inverter alone knows which limits it takes."""
    settings = p17_settings.settings_for(tuple(PI18_RATINGS))
    setting = {item.key: item for item in settings}["max_charging_current"]
    assert setting.options_in({}) == {}
    assert setting.decode("060", {}) is None
    assert setting.decode("060", PI18_ENUMERATIONS) == "060"


@pytest.mark.parametrize(
    ("tables", "command"),
    [(pi30_settings, "QMUCHGCR"), (p17_settings, "MCHGCR"), (p17_settings, "MUCHGCR")],
)
def test_an_enumeration_reply_with_no_values_is_an_error(tables, command) -> None:
    """An empty list is not an inverter that accepts nothing."""
    with pytest.raises(ValueError):
        tables.parse_enumeration(command, "   ")


@pytest.mark.parametrize("tables", [pi30_settings, p17_settings])
def test_only_the_declared_inquiries_enumerate_values(tables) -> None:
    """A caller cannot route an arbitrary reply through the parser."""
    with pytest.raises(ValueError):
        tables.parse_enumeration("QPIGS", "1 2 3")


def test_pi30_enumeration_is_space_separated_and_pi18_comma_separated() -> None:
    """Each protocol lists its accepted values in its own separator."""
    assert pi30_settings.parse_enumeration("QMUCHGCR", "002 010 120") == (
        "002",
        "010",
        "120",
    )
    assert p17_settings.parse_enumeration("MCHGCR", "010,020,030") == (
        "010",
        "020",
        "030",
    )


@pytest.mark.parametrize("command", ["QPIGS", "PCVV", "POPX", "POP0;QPIGS", ""])
def test_the_frame_builders_refuse_anything_but_a_declared_setter(command) -> None:
    """The transport refuses to carry a command no setting declares."""
    with pytest.raises(ProtocolError):
        build_pi30_setter(command)


def test_the_transport_carries_no_command_no_setting_uses() -> None:
    """The declared command surface is exactly the settings' own commands.

    The frame builders hold the list of setter names they will carry, and this
    holds that list against the tables from the other side: a name left in it
    after the setting using it was withdrawn would be a command this
    integration can still send and nothing can verify.
    """
    used_pi30 = {
        setting.command for setting in pi30_settings.settings_for(tuple(PI30_RATINGS))
    }
    used_pi18 = {
        setting.command for setting in p17_settings.settings_for(tuple(PI18_RATINGS))
    }
    assert used_pi30 == set(PI30_SETTER_COMMANDS)
    assert used_pi18 == set(P17_SETTER_COMMANDS)


@pytest.mark.parametrize(
    "command",
    [
        "PF",  # restore factory defaults
        "RTEY",  # reset the stored energy counters
        "RTDL",  # erase the data log
        "PBATCD011",  # can shut the unit down with no PV and no grid
        "DAT190518224530",  # the clock, whose digit count sources disagree on
        "PEA",  # an enable-disable flag, with no read-back this driver issues
        "PDA",
        "MNCHGC1120",  # two sources disagree on which limit it writes
        "PSAVE",
        "LON0",  # switches the load off
        "V230",
    ],
)
def test_no_destructive_or_undocumented_command_can_be_framed(command) -> None:
    """Commands that exist and are deliberately not implemented stay unreachable.

    Each of these is documented by one of the published tables, and each is
    either destructive, or something no read-back here could verify, or one
    whose own sources disagree. ``docs/LOCAL_MODE.md`` records why. None of
    them can be sent even by a caller that asks for it by name.
    """
    for builder in (build_pi30_setter, build_p17_setter):
        with pytest.raises(ProtocolError):
            builder(command)
