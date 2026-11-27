"""Publishing the inverter's own reading of a setting it reports locally (#93).

A setting the collector returns among the telemetry is as stale as the cloud
refresh that carried it. The account in #93 polls the cloud every ten minutes
because it times out at anything shorter, so its Output Priority sensor
showed a mode the inverter had left eight minutes earlier, while the local
link had the new value in two and a half seconds.

The whole risk in closing that gap is the vocabularies. A cloud control and a
local setting are the same register under two names and their option lists are
two more: devcode 2449 offers Output Source Priority as 12336, 12337 and
12338 - the two ASCII digits of the PI30 parameter read as one 16-bit number -
where POP takes 0, 1 and 2, and devcode 2477's charger list is renumbered
against the PI30 codes outright (#87). So most of these are about what must
*not* be rewritten.

The values here are devcode 2449's, from the download in
``docs/evidence/devcodes/analysis_2449_local_control.json``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dessmonitor.const import (
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_CONTROL,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    LOCAL_CONTROL_ENABLED,
)
from custom_components.dessmonitor.local.hybrid import DessMonitorHybridCoordinator
from custom_components.dessmonitor.local.pi30_settings import settings_for
from custom_components.dessmonitor.local.settings import cloud_option_for
from custom_components.dessmonitor.local.writer import SettingsSnapshot

CLOUD_SERIAL = "CLOUD-SERIAL"
LOCAL_SERIAL = "LOCAL-SERIAL"
DEVCODE = 2449

# The two controls the issue is about, as the committed download records them.
OUTPUT_PRIORITY_CONTROL = {
    "id": "bse_output_source_priority",
    "type": "options",
    "options": {
        "12336": "Utility Solar Bat",
        "12337": "Solar Utility Bat",
        "12338": "Solar Bat Utility",
    },
}
CHARGER_PRIORITY_CONTROL = {
    "id": "bat_charging_source",
    "type": "options",
    "options": {
        "12337": "Solar First",
        "12338": "Solar + Utility",
        "12339": "Only Solar Charging Permitted",
    },
}

# A 48 V QPIRI reply. Fields 16 and 17 are the two priorities, and both are
# overridden per test.
_RATINGS = (
    "230.0 21.7 230.0 50.0 21.7 5000 5000 48.0 46.0 42.0 56.4 54.0 2 030 "
    "080 0 0 2 0 1 0 0 27.0 0 0"
).split(" ")


def _hybrid(hass: HomeAssistant, *, control: bool = True, controls=None):
    """Create a hybrid coordinator for devcode 2449 without opening sockets."""
    api = MagicMock(token="token", secret="secret", close=AsyncMock())
    local_config = {
        CONF_LOCAL_LISTEN_IP: "127.0.0.1",
        CONF_LOCAL_COLLECTOR_IP: "127.0.0.2",
        CONF_LOCAL_TCP_PORT: 0,
        CONF_LOCAL_UDP_PORT: 9,
    }
    if control:
        local_config[CONF_LOCAL_CONTROL] = LOCAL_CONTROL_ENABLED
    coordinator = DessMonitorHybridCoordinator(hass, api, 600, local_config, "hybrid")
    coordinator.ctrl_field_cache = {
        CLOUD_SERIAL: (
            {
                "Output Source Priority": OUTPUT_PRIORITY_CONTROL,
                "Charging Source Priority": CHARGER_PRIORITY_CONTROL,
            }
            if controls is None
            else controls
        )
    }
    return coordinator


def _snapshot(**reported: str) -> SettingsSnapshot:
    settings = settings_for(tuple(_RATINGS))
    enumerations = {"QMUCHGCR": ("002", "010", "020", "030", "080")}
    values = {
        setting.key: decoded
        for setting in settings
        if (decoded := setting.decode(_RATINGS[setting.index], enumerations))
        is not None
    }
    values.update(reported)
    return SettingsSnapshot(settings, values, enumerations, ())


def _wire_local(coordinator, snapshot: SettingsSnapshot, *, healthy: bool = True):
    local = coordinator.locals[0]
    local.async_set_updated_data(
        {
            LOCAL_SERIAL: {
                "collector": {"pn": "COLLECTOR-1"},
                "device": {"devcode": 2452, "devaddr": 1},
                "data": [],
            }
        }
    )
    local._settings[LOCAL_SERIAL] = snapshot
    if not healthy:
        local.last_update_success = False
    return local


def _cloud(*points: tuple[str, str]) -> dict:
    return {
        CLOUD_SERIAL: {
            "collector": {"pn": "COLLECTOR-1"},
            "device": {"devcode": DEVCODE, "devaddr": 1, "alias": "Main"},
            "data": [{"title": title, "val": value, "unit": ""} for title, value in points],
        }
    }


def _values(merged: dict) -> dict[str, str]:
    return {point["title"]: point["val"] for point in merged[CLOUD_SERIAL]["data"]}


async def test_the_reported_lag_is_closed(hass: HomeAssistant) -> None:
    """The case the issue was opened for.

    The owner switched Output Source Priority from Utility Solar Bat to Solar
    Utility Bat, the local write verified in 2.5 s and the inverter reported
    "1", and the sensor kept the cloud's eight-minute-old word for it.
    """
    coordinator = _hybrid(hass)
    _wire_local(coordinator, _snapshot(output_source_priority="1"))

    merged = coordinator._overlay_local_settings(
        _cloud(("Output Source Priority", "Utility Solar Bat"))
    )

    assert _values(merged) == {"Output Source Priority": "Solar Utility Bat"}


async def test_the_label_written_is_the_platform_word_not_the_local_one(
    hass: HomeAssistant,
) -> None:
    """An automation comparing against the old string still matches.

    The PI30 command calls option 1 "Solar first" and the platform calls it
    "Solar Utility Bat", which the devcode profile maps on to
    "Solar → Utility → Battery". Publishing the local word would change what
    the sensor says on an installation that has always read the other.
    """
    coordinator = _hybrid(hass)
    _wire_local(coordinator, _snapshot(output_source_priority="1"))

    merged = coordinator._overlay_local_settings(
        _cloud(("Output Source Priority", "Solar Bat Utility"))
    )

    assert _values(merged)["Output Source Priority"] == "Solar Utility Bat"


async def test_a_control_paired_by_declaration_is_read_back_too(
    hass: HomeAssistant,
) -> None:
    """Devcode 2449's charger priority pairs on a declaration, not a name.

    The platform calls it "Charging Source Priority" and the command calls it
    "Charger Source Priority", one letter apart, so nothing was inferred and
    the profile declares it (#88). The reading is named after the command.
    """
    coordinator = _hybrid(hass)
    _wire_local(coordinator, _snapshot(charger_source_priority="1"))

    merged = coordinator._overlay_local_settings(
        _cloud(("Charger Source Priority", "Only Solar Charging Permitted"))
    )

    assert _values(merged)["Charger Source Priority"] == "Solar First"


async def test_nothing_is_rewritten_without_local_control(hass: HomeAssistant) -> None:
    """The option is off by default, so no upgrade starts doing this."""
    coordinator = _hybrid(hass, control=False)
    _wire_local(coordinator, _snapshot(output_source_priority="1"))

    merged = coordinator._overlay_local_settings(
        _cloud(("Output Source Priority", "Utility Solar Bat"))
    )

    assert _values(merged)["Output Source Priority"] == "Utility Solar Bat"


async def test_a_silent_collector_does_not_override_the_cloud(
    hass: HomeAssistant,
) -> None:
    """A read-back is only as good as the link that produced it.

    Keeping the last snapshot would publish a stale setting over a live cloud
    one for as long as the collector stayed down, which is the opposite of
    what this exists for.
    """
    coordinator = _hybrid(hass)
    _wire_local(coordinator, _snapshot(output_source_priority="1"), healthy=False)

    merged = coordinator._overlay_local_settings(
        _cloud(("Output Source Priority", "Utility Solar Bat"))
    )

    assert _values(merged)["Output Source Priority"] == "Utility Solar Bat"


async def test_an_unpaired_control_leaves_its_reading_alone(
    hass: HomeAssistant,
) -> None:
    """Nothing says a cloud control and a local setting are one register.

    With no declaration and no shared name there is no pairing, and the
    reading keeps the cloud's own figure. "Energy Mode" is not a name the
    PI30 table carries.
    """
    coordinator = _hybrid(
        hass,
        controls={
            "Energy Mode": {
                "id": "bse_energy_mode",
                "type": "options",
                "options": {"12336": "Utility Solar Bat", "12337": "Solar Utility Bat"},
            }
        },
    )
    _wire_local(coordinator, _snapshot(output_source_priority="1"))

    merged = coordinator._overlay_local_settings(
        _cloud(("Output Source Priority", "Utility Solar Bat"))
    )

    assert _values(merged)["Output Source Priority"] == "Utility Solar Bat"


async def test_a_reading_that_is_not_a_readback_is_never_touched(
    hass: HomeAssistant,
) -> None:
    """Only a reading already carrying one of that control's own labels moves.

    Grid Voltage is a measurement, not the read-back of a selection, and no
    option label is "234.0".
    """
    coordinator = _hybrid(hass)
    _wire_local(coordinator, _snapshot(output_source_priority="1"))

    merged = coordinator._overlay_local_settings(
        _cloud(("Grid Voltage", "234.0"), ("Battery Capacity", "71"))
    )

    assert _values(merged) == {"Grid Voltage": "234.0", "Battery Capacity": "71"}


async def test_a_label_two_controls_offer_is_left_alone(hass: HomeAssistant) -> None:
    """A shared label says nothing about which control a reading belongs to.

    Both lists here carry "Solar First", so a reading sitting at that word
    could be either register's read-back and is published as the cloud sent
    it.
    """
    coordinator = _hybrid(
        hass,
        controls={
            "Output Source Priority": {
                "id": "bse_output_source_priority",
                "type": "options",
                "options": {"12336": "Utility first", "12337": "Solar First"},
            },
            "Charging Source Priority": CHARGER_PRIORITY_CONTROL,
        },
    )
    _wire_local(
        coordinator,
        _snapshot(output_source_priority="0", charger_source_priority="3"),
    )

    merged = coordinator._overlay_local_settings(_cloud(("Whichever", "Solar First")))

    assert _values(merged)["Whichever"] == "Solar First"


def test_a_renumbered_option_list_resolves_to_nothing() -> None:
    """The dangerous half of #87, held at the translation itself.

    Devcode 2477's charger list is renumbered against the PI30 codes, so a
    code paired positionally would name an option the inverter is not set to
    and its own read-back would agree. The reverse translation is built out of
    the forward one, which pairs a selection only on a declaration or on a
    label that is the same word on both sides, so a list whose words differ
    pairs with nothing.
    """
    setting = next(
        item
        for item in settings_for(tuple(_RATINGS))
        if item.key == "charger_source_priority"
    )
    renumbered = {"0": "Solar priority", "1": "Utility priority"}

    assert cloud_option_for(setting, "1", renumbered) is None


def test_an_ambiguous_reverse_translation_resolves_to_nothing() -> None:
    """Two cloud codes meaning one local value is not an answer.

    A platform that offers the same option twice says nothing about which code
    the inverter's value came from, so the cloud's own figure stands.
    """
    setting = next(
        item
        for item in settings_for(tuple(_RATINGS))
        if item.key == "output_source_priority"
    )
    duplicated = {"12337": "Solar first", "12340": "Solar first"}

    assert cloud_option_for(setting, "1", duplicated) is None


def test_a_setpoint_is_not_read_back_this_way() -> None:
    """Only a selection has a vocabulary to translate.

    A voltage is a figure in both, and its reading is not an option label, so
    nothing here applies to one.
    """
    setting = next(
        item
        for item in settings_for(tuple(_RATINGS))
        if item.key == "battery_bulk_voltage"
    )

    assert cloud_option_for(setting, "56.4", {"56.4": "56.4"}) is None


@pytest.mark.parametrize(
    ("reported", "expected"),
    [("0", "12336"), ("1", "12337"), ("2", "12338")],
)
def test_the_ascii_digit_codes_pair_on_the_profile_declaration(
    reported: str, expected: str
) -> None:
    """Devcode 2449's codes are the PI30 digits read as a 16-bit number.

    "00" is 0x3030 = 12336. The profile declares the mapping, and the reverse
    translation reads that same declaration rather than a second table.
    """
    from custom_components.dessmonitor.device_support import local_control_options

    setting = next(
        item
        for item in settings_for(tuple(_RATINGS))
        if item.key == "output_source_priority"
    )
    declared = local_control_options(DEVCODE, "bse_output_source_priority")

    assert (
        cloud_option_for(
            setting,
            reported,
            OUTPUT_PRIORITY_CONTROL["options"],
            None,
            declared,
        )
        == expected
    )
