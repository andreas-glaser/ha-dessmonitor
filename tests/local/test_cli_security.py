"""Security regressions for contributor CLI failures and reports."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs

import aiohttp
import pytest


def _load_cli_module() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "cli" / "dessmonitor_cli.py"
    spec = importlib.util.spec_from_file_location("dessmonitor_test_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_transport_error_never_contains_signed_url_or_token() -> None:
    """aiohttp may embed its URL in errors; the CLI must replace that text."""
    cli_module = _load_cli_module()
    cli = cli_module.DessMonitorCLI()
    cli.token = "PRIVATE-TOKEN"
    cli.secret = "PRIVATE-SECRET"
    cli.token_expires = int(time.time()) + 60

    class FailingSession:
        def get(self, _url: str):
            raise aiohttp.ClientConnectionError(
                "failed https://example.invalid/?token=PRIVATE-TOKEN"
            )

    cli.session = FailingSession()
    with pytest.raises(RuntimeError) as caught:
        await cli._make_request("queryPlants", {"pagesize": 50})
    message = str(caught.value)
    assert message == (
        "API transport failed for action queryPlants (ClientConnectionError)"
    )
    assert "PRIVATE" not in message
    assert "http" not in message.lower()


def test_private_writer_refuses_symlink(tmp_path: Path) -> None:
    """Analysis and template output cannot overwrite an arbitrary link target."""
    cli_module = _load_cli_module()
    target = tmp_path / "target"
    target.write_text("unchanged")
    link = tmp_path / "result"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic"):
        cli_module._write_private_json(link, {"changed": True})
    assert target.read_text() == "unchanged"


async def test_sanitized_analysis_log_does_not_print_device_serial(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Support-bundle progress output must not reveal the selected identity."""
    cli_module = _load_cli_module()
    cli = cli_module.DessMonitorCLI()
    serial = "PRIVATE-DEVICE-SERIAL"
    cli._find_device_info = AsyncMock(return_value=None)
    cli.get_device_data = AsyncMock(return_value=[])

    with caplog.at_level(logging.INFO):
        assert await cli.analyze_device_for_devcode(serial) == {}

    assert serial not in caplog.text


@pytest.mark.parametrize("profile", ["dessmonitor_ess", "shinemonitor_solar"])
async def test_cli_auth_and_refresh_use_selected_profile(
    cloud_transport, tmp_path, profile
):
    module = _load_cli_module()
    cli = module.DessMonitorCLI(api_profile=profile)
    cli.session, connector = cloud_transport
    cli.config_file = tmp_path / "credentials.json"
    for _ in range(2):
        assert await cli.authenticate("test user/a+b", " password ", "test-key")
        request = connector.requests[-1]
        target = request.split(b"\r\n", 1)[0].decode().split(" ")[1]
        query = target.split("?", 1)[1]
        params = parse_qs(query)
        profile_data = module._CONSTANTS.API_PROFILES[profile]
        assert params["action"] == [profile_data["auth_action"]]
        assert params["source"] == [profile_data["source"]]
        assert "token" not in params
        action = "&action=" + query.split("&action=", 1)[1]
        pwd_hash = hashlib.sha1(b" password ").hexdigest()
        expected = hashlib.sha1(
            (params["salt"][0] + pwd_hash + action).encode()
        ).hexdigest()
        assert params["sign"] == [expected]
    saved = json.loads(cli.config_file.read_text())
    assert saved["api_profile"] == profile
    assert cli.config_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "saved_profile", [None, "dessmonitor_ess", "shinemonitor_solar"]
)
async def test_cli_restores_profile_before_signing_queries(
    cloud_transport, tmp_path, saved_profile
):
    module = _load_cli_module()
    cli = module.DessMonitorCLI()
    cli.session, connector = cloud_transport
    cli.config_file = tmp_path / "credentials.json"
    data = {
        "username": "test-user",
        "password": "test-password",
        "company_key": "test-key",
        "token": "test-token",
        "secret": "test-secret",
        "token_expires": 2**31,
    }
    if saved_profile is not None:
        data["api_profile"] = saved_profile
    cli._write_private_config(data)
    await cli.get_device_parameters("test-pn", 518, 1, "test-sn")
    request = connector.requests[-1]
    target = request.split(b"\r\n", 1)[0].decode().split(" ")[1]
    query = parse_qs(target.split("?", 1)[1])
    expected_profile = module._CONSTANTS.API_PROFILES[
        saved_profile or "dessmonitor_ess"
    ]
    assert query["source"] == [expected_profile["source"]]
    assert f"Host: {expected_profile['base_url'].split('/')[2]}\r\n".encode() in request
    assert len(connector.requests) == 1


async def test_cli_rejects_other_platform_credentials_before_request(tmp_path):
    module = _load_cli_module()
    cli = module.DessMonitorCLI(api_profile="shinemonitor_solar")
    cli.session = MagicMock()
    cli.config_file = tmp_path / "credentials.json"
    cli._write_private_config(
        {
            "api_profile": "dessmonitor_ess",
            "token": "test-token",
            "secret": "test-secret",
            "token_expires": 2**31,
        }
    )
    with pytest.raises(ValueError, match="another platform"):
        await cli.authenticate_from_config()
    cli.session.get.assert_not_called()
    assert cli.token is None


def test_cli_profile_selection_keeps_existing_default():
    parser = _load_cli_module().setup_argparser()
    args = parser.parse_args(["auth", "--username", "test-user"])
    assert args.api_profile == "dessmonitor_ess"
    args = parser.parse_args(
        ["auth", "--username", "test-user", "--api-profile", "shinemonitor_solar"]
    )
    assert args.api_profile == "shinemonitor_solar"
    with pytest.raises(SystemExit):
        parser.parse_args(["auth", "--username", "test-user", "--api-profile", "typo"])


@pytest.mark.parametrize(
    "auth_data",
    [
        {"token": "test-token", "expire": 3600},
        {"token": "test-token", "secret": "test-secret"},
        {"token": "test-token", "secret": "test-secret", "expire": -1},
    ],
)
async def test_cli_rejects_incomplete_authentication(
    cloud_transport, tmp_path, auth_data
):
    cli = _load_cli_module().DessMonitorCLI()
    cli.session, connector = cloud_transport
    connector.payload = {"err": 0, "dat": auth_data}
    cli.config_file = tmp_path / "credentials.json"
    assert not await cli.authenticate("test-user", "test-password", "test-key")
    assert cli.token is None
    assert cli.secret is None
    assert not cli.config_file.exists()
