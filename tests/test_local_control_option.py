"""The option that decides whether an entry may write over the local link.

Local mode was read-only for its whole life, so the one thing these have to
establish is that an installation which never touches this option keeps
exactly the behaviour it already had.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor.const import (
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_COLLECTOR_IPS,
    CONF_LOCAL_CONTROL,
    CONF_LOCAL_DEVICE_ADDRESS,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_MODE,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_REDIRECT_CONFIRMED,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    CONNECTION_TYPE_LOCAL,
    DEFAULT_LOCAL_CONTROL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOCAL_CONTROL_DISABLED,
    LOCAL_CONTROL_ENABLED,
    LOCAL_CONTROL_OPTIONS,
    LOCAL_MODE_PREFER_LOCAL,
)


def test_writing_settings_is_not_the_default() -> None:
    """An upgrade must not start accepting writes on its own."""
    assert DEFAULT_LOCAL_CONTROL == LOCAL_CONTROL_DISABLED
    assert set(LOCAL_CONTROL_OPTIONS) == {
        LOCAL_CONTROL_DISABLED,
        LOCAL_CONTROL_ENABLED,
    }


def _local_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.10.50",
        },
        options=options or {},
        unique_id="local:192.168.10.50",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.usefixtures("mock_setup_entry")
async def test_a_local_entry_can_turn_local_control_on(hass: HomeAssistant) -> None:
    """The option is offered on the entry's own options form, defaulting to off."""
    entry = _local_entry(hass)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] is FlowResultType.FORM
    assert CONF_LOCAL_CONTROL in form["data_schema"].schema

    done = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            CONF_LOCAL_POLL_INTERVAL: "5",
            CONF_LOCAL_DEVICE_ADDRESS: 0,
            CONF_LOCAL_CONTROL: LOCAL_CONTROL_ENABLED,
        },
    )

    assert done["data"][CONF_LOCAL_CONTROL] == LOCAL_CONTROL_ENABLED


@pytest.mark.usefixtures("mock_setup_entry")
async def test_a_local_entry_that_says_nothing_stays_read_only(
    hass: HomeAssistant,
) -> None:
    """Saving the form without touching the choice keeps writes off."""
    entry = _local_entry(hass)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    done = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {CONF_LOCAL_POLL_INTERVAL: "5", CONF_LOCAL_DEVICE_ADDRESS: 0},
    )

    assert done["data"][CONF_LOCAL_CONTROL] == LOCAL_CONTROL_DISABLED


@pytest.mark.usefixtures("mock_setup_entry")
async def test_an_unrecognised_stored_choice_is_treated_as_read_only(
    hass: HomeAssistant,
) -> None:
    """A value this version does not know is never read as permission to write.

    An option written by a later version, or edited by hand, must fail closed.
    """
    entry = _local_entry(hass, {CONF_LOCAL_CONTROL: "something-else"})

    form = await hass.config_entries.options.async_init(entry.entry_id)
    done = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {CONF_LOCAL_POLL_INTERVAL: "5", CONF_LOCAL_DEVICE_ADDRESS: 0},
    )

    assert done["data"][CONF_LOCAL_CONTROL] == LOCAL_CONTROL_DISABLED


@pytest.mark.usefixtures("mock_setup_entry")
async def test_a_hybrid_entry_can_turn_local_control_on(hass: HomeAssistant) -> None:
    """The same choice appears on the preferred-local form a cloud entry uses."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        },
        options={
            CONF_UPDATE_INTERVAL: 600,
            CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL,
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IPS: ["192.168.10.50"],
            CONF_LOCAL_POLL_INTERVAL: 10,
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    local_form = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {CONF_UPDATE_INTERVAL: "600", CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL},
    )
    assert CONF_LOCAL_CONTROL in local_form["data_schema"].schema

    done = await hass.config_entries.options.async_configure(
        local_form["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IPS: "192.168.10.50",
            CONF_LOCAL_POLL_INTERVAL: "10",
            CONF_LOCAL_DEVICE_ADDRESS: 0,
            CONF_LOCAL_CONTROL: LOCAL_CONTROL_ENABLED,
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )

    assert done["data"][CONF_LOCAL_CONTROL] == LOCAL_CONTROL_ENABLED
    # The rest of the preferred-local configuration is untouched by the choice.
    assert done["data"][CONF_LOCAL_COLLECTOR_IPS] == ["192.168.10.50"]
    assert done["data"][CONF_UPDATE_INTERVAL] == 600


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_setup_does_not_ask_about_writing_settings(
    hass: HomeAssistant,
) -> None:
    """Setting up local telemetry is not the moment to decide about writes.

    An owner proves local telemetry works first; turning writes on afterwards
    is a deliberate second step, taken on the options form.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    local = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": CONNECTION_TYPE_LOCAL}
    )

    assert local["type"] is FlowResultType.FORM
    assert CONF_LOCAL_CONTROL not in local["data_schema"].schema
