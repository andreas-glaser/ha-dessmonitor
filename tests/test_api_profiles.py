"""API profile behaviour: identity, transport encoding and token isolation.

Each profile keeps its host, signature, and cached authentication state isolated.
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.dessmonitor.api import DessMonitorAPI
from custom_components.dessmonitor.const import (
    API_PROFILE_DESSMONITOR_ESS,
    API_PROFILE_SHINEMONITOR_SOLAR,
    API_PROFILES,
    DEFAULT_API_PROFILE,
    resolve_api_profile,
)


class _CapturingSession:
    """Minimal session stand-in that records requested URLs."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.requested: list[Any] = []
        self._payload = payload or {"err": 0, "dat": {}}

    def get(self, url: Any, **_: Any) -> Any:
        self.requested.append(url)
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = AsyncMock(return_value=self._payload)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    @property
    def last_url(self) -> str:
        return str(self.requested[-1])


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest().lower()


@pytest.mark.parametrize(
    ("profile", "host", "action", "source"),
    [
        (
            API_PROFILE_DESSMONITOR_ESS,
            "api.dessmonitor.com",
            "authSource",
            "1",
        ),
        (
            API_PROFILE_SHINEMONITOR_SOLAR,
            "ios.shinemonitor.com",
            "auth",
            "0",
        ),
    ],
)
async def test_each_profile_authenticates_against_its_own_backend(
    profile: str, host: str, action: str, source: str
) -> None:
    """Host, auth action and source travel together, per profile."""
    session = _CapturingSession(
        {"err": 0, "dat": {"token": "t", "secret": "s", "expire": 3600}}
    )
    api = DessMonitorAPI("user", "pw", session=session, api_profile=profile)

    await api.authenticate()

    url = session.last_url
    assert host in url
    assert f"&action={action}&" in url
    assert f"&source={source}" in url


def test_no_profile_impersonates_a_third_party_application() -> None:
    """The integration identifies as itself.

    ios.shinemonitor.com accepts action=auth&source=0 with our own _app_id_ --
    verified against a live account -- so there is no reason to send the mobile
    app's bundle id.
    """
    for profile in API_PROFILES.values():
        assert profile["app_id"] == "ha-dessmonitor"


def test_default_profile_is_the_pre_existing_behaviour() -> None:
    """An entry that predates the selector must not change backend."""
    assert DEFAULT_API_PROFILE == API_PROFILE_DESSMONITOR_ESS
    assert API_PROFILES[DEFAULT_API_PROFILE]["auth_action"] == "authSource"
    assert resolve_api_profile({}) == DEFAULT_API_PROFILE


def test_legacy_account_mode_key_still_resolves() -> None:
    """Entries created by the earlier revision of this branch keep working."""
    assert resolve_api_profile({"account_mode": "end_user"}) == (
        API_PROFILE_SHINEMONITOR_SOLAR
    )
    assert resolve_api_profile({"account_mode": "distributor"}) == (
        API_PROFILE_DESSMONITOR_ESS
    )
    # an explicit new-style value always wins
    assert (
        resolve_api_profile(
            {"api_profile": API_PROFILE_DESSMONITOR_ESS, "account_mode": "end_user"}
        )
        == API_PROFILE_DESSMONITOR_ESS
    )


def assert_wire_signature(request, signing_prefix):
    target = request.split(b"\r\n", 1)[0].decode().split(" ")[1]
    query = target.split("?", 1)[1]
    before, after = query.split("&action=", 1)
    parameters = dict(part.split("=", 1) for part in before.split("&"))
    assert parameters["sign"] == _sha1(
        parameters["salt"] + signing_prefix + "&action=" + after
    )
    return after


@pytest.mark.parametrize("profile", API_PROFILES)
@pytest.mark.parametrize(
    "username", ["user", "a b/c?d+e&f=%#", "Jos\u00e9", "a+b", "a&b", "a/b", "a?b"]
)
async def test_auth_and_control_signatures_at_transport(
    cloud_transport, profile, username
):
    session, connector = cloud_transport
    api = DessMonitorAPI(username, " password ", session=session, api_profile=profile)
    await api.authenticate()
    action = assert_wire_signature(connector.requests[-1], _sha1(" password "))
    assert action.startswith(API_PROFILES[profile]["auth_action"] + "&")
    assert f"Host: {api.base_url.split('/')[2]}\r\n".encode() in connector.requests[-1]
    await api.set_device_control_value(
        "PN/1", 518, 1, "SN?2", "field", "a b/c?d+e&f=%#"
    )
    action = assert_wire_signature(connector.requests[-1], "test-secrettest-token")
    assert action.startswith("ctrlDevice&")
    assert f"&source={API_PROFILES[profile]['source']}" in action
    api.token_expire = 1
    await api.get_device_control_value("PN/1", 518, 1, "SN?2", "field")
    assert_wire_signature(connector.requests[-2], _sha1(" password "))
    assert_wire_signature(connector.requests[-1], "test-secrettest-token")


async def test_cached_token_from_another_profile_is_discarded() -> None:
    """A token is only valid on the host that issued it."""
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={
            "token": "t",
            "secret": "s",
            "token_expire": 2**31,
            "api_profile": API_PROFILE_DESSMONITOR_ESS,
        }
    )
    store.async_save = AsyncMock()
    store.async_remove = AsyncMock()
    api = DessMonitorAPI(
        "user",
        "pw",
        session=MagicMock(),
        store=store,
        api_profile=API_PROFILE_SHINEMONITOR_SOLAR,
    )

    assert await api.load_saved_token() is False
    assert api.token is None


async def test_cached_token_from_the_same_profile_is_used() -> None:
    """The isolation must not throw away a perfectly good token."""
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={
            "token": "t",
            "secret": "s",
            "token_expire": 2**31,
            "api_profile": API_PROFILE_SHINEMONITOR_SOLAR,
        }
    )
    store.async_save = AsyncMock()
    api = DessMonitorAPI(
        "user",
        "pw",
        session=MagicMock(),
        store=store,
        api_profile=API_PROFILE_SHINEMONITOR_SOLAR,
    )

    assert await api.load_saved_token() is True
    assert api.token == "t"


async def test_token_cached_before_this_field_existed_belongs_to_the_default() -> None:
    """No profile recorded means it was written by the pre-profile code."""
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={"token": "t", "secret": "s", "token_expire": 2**31}
    )
    store.async_save = AsyncMock()
    api = DessMonitorAPI(
        "user", "pw", session=MagicMock(), store=store, api_profile=DEFAULT_API_PROFILE
    )

    assert await api.load_saved_token() is True


async def test_saved_token_records_its_profile() -> None:
    """Otherwise the check above has nothing to compare against."""
    store = MagicMock()
    store.async_save = AsyncMock()
    session = _CapturingSession(
        {"err": 0, "dat": {"token": "t", "secret": "s", "expire": 3600}}
    )
    api = DessMonitorAPI(
        "user",
        "pw",
        session=session,
        store=store,
        api_profile=API_PROFILE_SHINEMONITOR_SOLAR,
    )

    await api.authenticate()

    saved = store.async_save.await_args.args[0]
    assert saved["api_profile"] == API_PROFILE_SHINEMONITOR_SOLAR


@pytest.mark.parametrize("profile", ["typo", "", None, []])
def test_explicit_unknown_profile_is_rejected(profile) -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="Unsupported API profile"):
        DessMonitorAPI(
            "test-user", "test-password", session=session, api_profile=profile
        )
    session.get.assert_not_called()
    with pytest.raises(ValueError, match="Unsupported API profile"):
        resolve_api_profile({"api_profile": profile})


@pytest.mark.parametrize("saved_profile", [None, API_PROFILE_DESSMONITOR_ESS])
async def test_solar_rejects_legacy_and_other_backend_tokens(saved_profile) -> None:
    data = {"token": "test-token", "secret": "test-secret", "token_expire": 2**31}
    if saved_profile is not None:
        data["api_profile"] = saved_profile
    store = MagicMock()
    store.async_load = AsyncMock(return_value=data)
    store.async_remove = AsyncMock()
    api = DessMonitorAPI(
        "test-user",
        "test-password",
        session=MagicMock(),
        store=store,
        api_profile=API_PROFILE_SHINEMONITOR_SOLAR,
    )
    assert not await api.load_saved_token()
    assert api.token is None
    assert api.secret is None
    store.async_remove.assert_awaited_once()


@pytest.mark.parametrize("payload", [{"title": []}, ["bad-point"], [{"title": None}]])
async def test_malformed_telemetry_is_rejected_at_the_api_boundary(
    cloud_transport, payload
) -> None:
    from custom_components.dessmonitor.api import DessMonitorError

    session, connector = cloud_transport
    connector.payload = {"err": 0, "dat": payload}
    api = DessMonitorAPI("test-user", "test-password", session=session)
    api.token, api.secret = "test-token", "test-secret"
    with pytest.raises(DessMonitorError, match="Invalid device data response"):
        await api.get_device_last_data("test-pn", 518, 1, "test-sn")


@pytest.mark.parametrize(
    "auth_data",
    [
        {"token": "test-token", "expire": 3600},
        {"token": "test-token", "secret": "test-secret"},
        {"token": "test-token", "secret": "test-secret", "expire": -1},
    ],
)
async def test_invalid_auth_response_does_not_create_a_session(
    cloud_transport, auth_data
):
    from custom_components.dessmonitor.api import DessMonitorError

    session, connector = cloud_transport
    connector.payload = {"err": 0, "dat": auth_data}
    api = DessMonitorAPI("test-user", "test-password", session=session)
    with pytest.raises(DessMonitorError, match="Invalid authentication data"):
        await api.authenticate()
    assert api.token is None
    assert api.secret is None
