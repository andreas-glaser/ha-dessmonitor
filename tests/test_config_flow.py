"""Config-flow tests for stable frontend choices and stored values."""

from __future__ import annotations

import pytest
import voluptuous_serialize
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import config_validation as cv
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dessmonitor.const import (
    CONF_COMPANY_KEY,
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_COLLECTOR_IPS,
    CONF_LOCAL_DEVICE_CODE,
    CONF_LOCAL_EXPECTED_PN,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_MODE,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_REDIRECT_CONFIRMED,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_HYBRID,
    CONNECTION_TYPE_LOCAL,
    DEFAULT_COMPANY_KEY,
    DEFAULT_LOCAL_DEVICE_CODE,
    DEFAULT_LOCAL_POLL_INTERVAL,
    DEFAULT_LOCAL_TCP_PORT,
    DEFAULT_LOCAL_UDP_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOCAL_MODE_DISABLED,
    LOCAL_MODE_PREFER_LOCAL,
)

BASE_INPUT = {
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: "hunter2",
    CONF_COMPANY_KEY: DEFAULT_COMPANY_KEY,
}


def _form_default(result: dict, field: str) -> object:
    """Return the raw frontend default for one voluptuous field marker."""
    for marker in result["data_schema"].schema:
        if marker.schema == field:
            return marker.default()
    raise AssertionError(f"missing form field {field}")


def _serialized_form_field(result: dict, field: str) -> dict:
    """Return a field exactly as Home Assistant sends it to the frontend."""
    serialized = voluptuous_serialize.convert(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    return next(item for item in serialized if item["name"] == field)


async def _start_cloud_flow(hass: HomeAssistant) -> dict:
    """Open the connection menu and select the cloud path."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": CONNECTION_TYPE_CLOUD}
    )


async def _start_local_flow(hass: HomeAssistant, *, advanced: bool = False) -> dict:
    """Open the connection menu and select a local path."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "local_advanced" if advanced else CONNECTION_TYPE_LOCAL},
    )


async def _start_hybrid_flow(hass: HomeAssistant) -> dict:
    """Open the API-first guided flow with preferred local telemetry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": CONNECTION_TYPE_HYBRID}
    )


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
@pytest.mark.parametrize("submitted", ["300", 300])
async def test_user_flow_coerces_interval(
    hass: HomeAssistant, submitted: str | int
) -> None:
    """A string interval from the frontend is accepted and stored as int."""
    result = await _start_cloud_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**BASE_INPUT, CONF_UPDATE_INTERVAL: submitted}
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_UPDATE_INTERVAL] == 300
    assert isinstance(result2["data"][CONF_UPDATE_INTERVAL], int)
    assert result2["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_CLOUD


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
async def test_user_flow_uses_default_interval(hass: HomeAssistant) -> None:
    """Omitting the interval falls back to the integer default."""
    result = await _start_cloud_flow(hass)
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], BASE_INPUT
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_UPDATE_INTERVAL] == DEFAULT_UPDATE_INTERVAL


async def test_flow_version_stays_compatible_with_existing_entries() -> None:
    """Optional local settings must not force legacy API entries to migrate."""
    from custom_components.dessmonitor.config_flow import ConfigFlow

    assert ConfigFlow.VERSION == 1


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
async def test_guided_hybrid_flow_creates_api_entry_with_local_options(
    hass: HomeAssistant,
) -> None:
    """Hybrid starts with the API but makes its local preference explicit."""
    cloud_form = await _start_hybrid_flow(hass)
    assert cloud_form["step_id"] == CONNECTION_TYPE_HYBRID

    local_form = await hass.config_entries.flow.async_configure(
        cloud_form["flow_id"],
        {**BASE_INPUT, CONF_UPDATE_INTERVAL: "300"},
    )
    assert local_form["step_id"] == "hybrid_local"

    created = await hass.config_entries.flow.async_configure(
        local_form["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IPS: "192.168.10.50 192.168.10.51",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    await hass.async_block_till_done()

    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_CLOUD
    assert created["options"][CONF_LOCAL_MODE] == LOCAL_MODE_PREFER_LOCAL
    assert created["options"][CONF_LOCAL_COLLECTOR_IPS] == [
        "192.168.10.50",
        "192.168.10.51",
    ]
    assert CONF_PASSWORD not in created["options"]


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
async def test_user_flow_rejects_unknown_interval(hass: HomeAssistant) -> None:
    """Coercion must not weaken validation: a non-option value is rejected."""
    result = await _start_cloud_flow(hass)
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {**BASE_INPUT, CONF_UPDATE_INTERVAL: "999"}
        )


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize("submitted", ["600", 600])
async def test_options_flow_coerces_interval(
    hass: HomeAssistant, submitted: str | int
) -> None:
    """The options flow has the same int-keyed dropdown and must coerce too."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_INPUT, CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
        options={},
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert _form_default(result, CONF_UPDATE_INTERVAL) == "300"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: submitted}
    )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_UPDATE_INTERVAL] == 600
    assert isinstance(result2["data"][CONF_UPDATE_INTERVAL], int)
    assert result2["data"][CONF_LOCAL_MODE] == LOCAL_MODE_DISABLED


@pytest.mark.usefixtures("mock_setup_entry")
async def test_hybrid_options_serialize_saved_intervals_as_selected(
    hass: HomeAssistant,
) -> None:
    """Saved API and local intervals match their serialized radio values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_INPUT, CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
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

    result = await hass.config_entries.options.async_init(entry.entry_id)
    api_interval = _serialized_form_field(result, CONF_UPDATE_INTERVAL)
    assert api_interval["default"] == "600"
    assert all(
        isinstance(option["value"], str)
        for option in api_interval["selector"]["select"]["options"]
    )

    local_form = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: "600",
            CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL,
        },
    )
    local_interval = _serialized_form_field(local_form, CONF_LOCAL_POLL_INTERVAL)
    assert local_interval["default"] == "10"
    assert all(
        isinstance(option["value"], str)
        for option in local_interval["selector"]["select"]["options"]
    )


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_flow_uses_secure_easy_defaults(hass: HomeAssistant) -> None:
    """The normal local path asks only for addresses and explicit consent."""
    result = await _start_local_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert set(result["data_schema"].schema) == {
        CONF_LOCAL_LISTEN_IP,
        CONF_LOCAL_COLLECTOR_IP,
        CONF_LOCAL_REDIRECT_CONFIRMED,
    }

    created = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.10.50",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    await hass.async_block_till_done()

    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_LOCAL
    assert created["data"][CONF_LOCAL_TCP_PORT] == DEFAULT_LOCAL_TCP_PORT
    assert created["data"][CONF_LOCAL_UDP_PORT] == DEFAULT_LOCAL_UDP_PORT
    assert created["data"][CONF_LOCAL_DEVICE_CODE] == DEFAULT_LOCAL_DEVICE_CODE
    assert created["data"][CONF_LOCAL_POLL_INTERVAL] == DEFAULT_LOCAL_POLL_INTERVAL
    assert CONF_LOCAL_REDIRECT_CONFIRMED not in created["data"]


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_flow_requires_redirect_confirmation(hass: HomeAssistant) -> None:
    """A collector cannot be redirected without deliberate user consent."""
    result = await _start_local_flow(hass)
    retried = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.10.50",
            CONF_LOCAL_REDIRECT_CONFIRMED: False,
        },
    )
    assert retried["type"] is FlowResultType.FORM
    assert retried["errors"] == {
        CONF_LOCAL_REDIRECT_CONFIRMED: "redirect_not_confirmed"
    }


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_flow_rejects_unsafe_addresses(hass: HomeAssistant) -> None:
    """Non-LAN addresses never reach the socket layer."""
    result = await _start_local_flow(hass)
    retried = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "0.0.0.0",
            CONF_LOCAL_COLLECTOR_IP: "224.0.0.1",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert retried["errors"] == {
        CONF_LOCAL_LISTEN_IP: "invalid_ip",
        CONF_LOCAL_COLLECTOR_IP: "invalid_ip",
    }


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_flow_rejects_public_and_same_host_addresses(
    hass: HomeAssistant,
) -> None:
    """Callback datagrams cannot target public IPs or Home Assistant itself."""
    result = await _start_local_flow(hass)
    public = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "203.0.113.5",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert public["errors"] == {CONF_LOCAL_COLLECTOR_IP: "invalid_ip"}

    same_host = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.10.2",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert same_host["errors"] == {
        CONF_LOCAL_COLLECTOR_IP: "collector_is_home_assistant"
    }


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_advanced_flow_stores_overrides(hass: HomeAssistant) -> None:
    """Unusual hardware can override ports, polling, device code, and ID pin."""
    result = await _start_local_flow(hass, advanced=True)
    created = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.10.50",
            CONF_LOCAL_EXPECTED_PN: " PN-EXPECTED ",
            CONF_LOCAL_TCP_PORT: "18899",
            CONF_LOCAL_UDP_PORT: "58898",
            CONF_LOCAL_DEVICE_CODE: "2452",
            CONF_LOCAL_POLL_INTERVAL: "10",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_LOCAL_EXPECTED_PN] == "PN-EXPECTED"
    assert created["data"][CONF_LOCAL_TCP_PORT] == 18899
    assert created["data"][CONF_LOCAL_DEVICE_CODE] == 2452


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_advanced_validation_stays_on_advanced_form(
    hass: HomeAssistant,
) -> None:
    """An advanced-form error retains every expert field and its step ID."""
    result = await _start_local_flow(hass, advanced=True)
    retried = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "not-an-ip",
            CONF_LOCAL_EXPECTED_PN: "",
            CONF_LOCAL_TCP_PORT: 8899,
            CONF_LOCAL_UDP_PORT: 58899,
            CONF_LOCAL_DEVICE_CODE: 0,
            CONF_LOCAL_POLL_INTERVAL: 5,
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert retried["step_id"] == "local_advanced"
    assert CONF_LOCAL_DEVICE_CODE in retried["data_schema"].schema


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_entry_can_be_reconfigured(hass: HomeAssistant) -> None:
    """Core local network settings use HA's native reconfigure flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.10.50",
            CONF_LOCAL_TCP_PORT: DEFAULT_LOCAL_TCP_PORT,
            CONF_LOCAL_UDP_PORT: DEFAULT_LOCAL_UDP_PORT,
            CONF_LOCAL_DEVICE_CODE: DEFAULT_LOCAL_DEVICE_CODE,
            CONF_LOCAL_POLL_INTERVAL: DEFAULT_LOCAL_POLL_INTERVAL,
            CONF_LOCAL_EXPECTED_PN: "",
        },
        unique_id="local:192.168.10.50",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["step_id"] == "reconfigure"

    updated = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.20.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.20.60",
            CONF_LOCAL_EXPECTED_PN: "EXPECTED-PN",
            CONF_LOCAL_TCP_PORT: 18899,
            CONF_LOCAL_UDP_PORT: 58898,
            CONF_LOCAL_DEVICE_CODE: 2376,
            CONF_LOCAL_POLL_INTERVAL: 10,
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert updated["type"] is FlowResultType.ABORT
    assert updated["reason"] == "reconfigure_successful"
    assert entry.unique_id == "local:192.168.20.60"
    assert entry.data[CONF_LOCAL_COLLECTOR_IP] == "192.168.20.60"
    assert entry.data[CONF_LOCAL_EXPECTED_PN] == "EXPECTED-PN"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_local_options_coerce_poll_interval(hass: HomeAssistant) -> None:
    """Local options retain frontend string coercion."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IP: "192.168.10.50",
            CONF_LOCAL_POLL_INTERVAL: DEFAULT_LOCAL_POLL_INTERVAL,
        },
        options={},
        unique_id="local:192.168.10.50",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "local"
    created = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCAL_POLL_INTERVAL: "10"}
    )
    assert created["data"][CONF_LOCAL_POLL_INTERVAL] == 10


@pytest.mark.usefixtures("mock_setup_entry")
async def test_cloud_options_enable_preferred_local(hass: HomeAssistant) -> None:
    """A cloud entry can add local telemetry without creating duplicate entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_INPUT, CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
        options={},
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    local_form = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: "300",
            CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL,
        },
    )
    assert local_form["type"] is FlowResultType.FORM
    assert local_form["step_id"] == "hybrid_local"
    assert _form_default(local_form, CONF_LOCAL_POLL_INTERVAL) == "5"

    created = await hass.config_entries.options.async_configure(
        local_form["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IPS: "192.168.10.50, 192.168.10.51",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_LOCAL_MODE] == LOCAL_MODE_PREFER_LOCAL
    assert created["data"][CONF_LOCAL_COLLECTOR_IPS] == [
        "192.168.10.50",
        "192.168.10.51",
    ]
    assert created["data"][CONF_LOCAL_DEVICE_CODE] == DEFAULT_LOCAL_DEVICE_CODE


@pytest.mark.usefixtures("mock_setup_entry")
async def test_cloud_options_reject_public_collector_list(
    hass: HomeAssistant,
) -> None:
    """Every hybrid callback target must be a distinct private address."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_INPUT, CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
        options={},
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    local_form = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: 300,
            CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL,
        },
    )
    retried = await hass.config_entries.options.async_configure(
        local_form["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.10.2",
            CONF_LOCAL_COLLECTOR_IPS: "192.168.10.50, 203.0.113.1",
            CONF_LOCAL_REDIRECT_CONFIRMED: True,
        },
    )
    assert retried["errors"] == {CONF_LOCAL_COLLECTOR_IPS: "invalid_ip_list"}


@pytest.mark.usefixtures("mock_setup_entry")
async def test_hybrid_validation_preserves_entered_collector_list(
    hass: HomeAssistant,
) -> None:
    """A missed confirmation must not force users to retype collector IPs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_INPUT, CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
        options={},
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    local_form = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: 300,
            CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL,
        },
    )
    retried = await hass.config_entries.options.async_configure(
        local_form["flow_id"],
        {
            CONF_LOCAL_LISTEN_IP: "192.168.50.20",
            CONF_LOCAL_COLLECTOR_IPS: "192.168.10.50, 192.168.10.51",
            CONF_LOCAL_POLL_INTERVAL: 10,
            CONF_LOCAL_REDIRECT_CONFIRMED: False,
        },
    )

    defaults = retried["data_schema"]({})
    assert retried["errors"] == {
        CONF_LOCAL_REDIRECT_CONFIRMED: "redirect_not_confirmed"
    }
    assert defaults[CONF_LOCAL_LISTEN_IP] == "192.168.50.20"
    assert defaults[CONF_LOCAL_COLLECTOR_IPS] == (
        "192.168.10.50, 192.168.10.51"
    )
    assert defaults[CONF_LOCAL_POLL_INTERVAL] == "10"
    assert defaults[CONF_LOCAL_REDIRECT_CONFIRMED] is False


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
async def test_cloud_flow_stores_the_selected_api_profile(
    hass: HomeAssistant,
) -> None:
    """Choosing the solar platform must survive into the entry data."""
    from custom_components.dessmonitor.const import (
        API_PROFILE_SHINEMONITOR_SOLAR,
        CONF_API_PROFILE,
    )

    result = await _start_cloud_flow(hass)
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**BASE_INPUT, CONF_API_PROFILE: API_PROFILE_SHINEMONITOR_SOLAR},
    )
    await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_API_PROFILE] == API_PROFILE_SHINEMONITOR_SOLAR


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
async def test_cloud_flow_defaults_to_the_pre_existing_platform(
    hass: HomeAssistant,
) -> None:
    """Not choosing anything must reproduce the behaviour before the selector."""
    from custom_components.dessmonitor.const import (
        CONF_API_PROFILE,
        DEFAULT_API_PROFILE,
        resolve_api_profile,
    )

    result = await _start_cloud_flow(hass)
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], BASE_INPUT
    )
    await hass.async_block_till_done()

    assert result2["data"][CONF_API_PROFILE] == DEFAULT_API_PROFILE
    assert resolve_api_profile(result2["data"]) == DEFAULT_API_PROFILE


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
async def test_same_username_can_exist_on_both_platforms(
    hass: HomeAssistant,
) -> None:
    """The unique ID carries the profile, so the second entry is not a dupe."""
    from custom_components.dessmonitor.const import (
        API_PROFILE_SHINEMONITOR_SOLAR,
        CONF_API_PROFILE,
    )

    first = await _start_cloud_flow(hass)
    created = await hass.config_entries.flow.async_configure(
        first["flow_id"], BASE_INPUT
    )
    await hass.async_block_till_done()
    assert created["type"] is FlowResultType.CREATE_ENTRY

    second = await _start_cloud_flow(hass)
    other = await hass.config_entries.flow.async_configure(
        second["flow_id"],
        {**BASE_INPUT, CONF_API_PROFILE: API_PROFILE_SHINEMONITOR_SOLAR},
    )
    await hass.async_block_till_done()

    assert other["type"] is FlowResultType.CREATE_ENTRY
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len({entry.unique_id for entry in entries}) == 2


@pytest.mark.usefixtures("mock_validate_input", "mock_setup_entry")
async def test_default_profile_keeps_the_bare_username_as_unique_id(
    hass: HomeAssistant,
) -> None:
    """Entries created before the selector must not be orphaned by it."""
    result = await _start_cloud_flow(hass)
    await hass.config_entries.flow.async_configure(result["flow_id"], BASE_INPUT)
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == BASE_INPUT[CONF_USERNAME]
