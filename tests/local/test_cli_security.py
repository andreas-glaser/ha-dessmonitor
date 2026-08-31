"""Security regressions for contributor CLI failures and reports."""

from __future__ import annotations

import importlib.util
import logging
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

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
