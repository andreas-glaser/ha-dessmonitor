"""API profile behaviour: identity, transport encoding and token isolation.

These cover the review points on PR #31: that each profile authenticates with
its own host/action/source, that the string we sign is byte-for-byte the string
aiohttp transmits, and that a cached token never crosses profiles.
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yarl

from custom_components.dessmonitor.api import DessMonitorAPI
from custom_components.dessmonitor.const import (
    API_PROFILE_DESSMONITOR_ESS,
    API_PROFILE_SHINEMONITOR_SOLAR,
    API_PROFILES,
    DEFAULT_API_PROFILE,
    resolve_api_profile,
)


class _CapturingSession:
    """Minimal aiohttp stand-in that records what would go on the wire."""

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


# --- profiles ---------------------------------------------------------------


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


# --- transport encoding (review point 5) ------------------------------------


@pytest.mark.parametrize(
    "username",
    ["Fabio Trentini", "a+b", "a&b", "José", "a/b", "a?b", "a b/c?d+e"],
)
async def test_signature_matches_the_bytes_actually_transmitted(
    username: str,
) -> None:
    """The signed action string must survive yarl untouched.

    quote_plus and yarl's requoting agree on most characters but diverge on "/"
    and "?", where yarl turns %2F and %3F back into the bare character. Signing
    one string and sending another is rejected as ERR_PASSWORD_VERIF_FAIL, so
    this recomputes the signature from the URL that reaches the session.
    """
    session = _CapturingSession(
        {"err": 0, "dat": {"token": "t", "secret": "s", "expire": 3600}}
    )
    api = DessMonitorAPI(
        username, "pw", session=session, api_profile=API_PROFILE_SHINEMONITOR_SOLAR
    )

    await api.authenticate()

    sent = session.requested[-1]
    assert isinstance(sent, yarl.URL), "URL must be pre-encoded for aiohttp"
    # yarl must not have rewritten anything on its way out
    assert str(sent) == str(yarl.URL(str(sent), encoded=True))

    raw = str(sent)
    query = raw.split("?", 1)[1]
    parts = query.split("&")
    sign = next(p.split("=", 1)[1] for p in parts if p.startswith("sign="))
    salt = next(p.split("=", 1)[1] for p in parts if p.startswith("salt="))
    action_string = "&" + "&".join(
        p for p in parts if not p.startswith(("sign=", "salt="))
    )

    expected = _sha1(f"{salt}{_sha1('pw')}{action_string}")
    assert sign == expected


# --- token isolation (review point 7) ---------------------------------------


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
