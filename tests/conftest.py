"""Global pytest fixtures."""

from __future__ import annotations

import threading
from functools import wraps

import pytest
from _pytest.monkeypatch import MonkeyPatch

from .common import load_fixture, load_json_fixture

pytest_plugins = ("pytest_homeassistant_custom_component",)


@pytest.fixture
def fixture_loader():
    """Return a callable that loads raw fixture text."""

    def _loader(name: str) -> str:
        return load_fixture(name)

    return _loader


@pytest.fixture
def json_fixture_loader():
    """Return a callable that loads JSON fixtures."""

    def _loader(name: str):
        return load_json_fixture(name)

    return _loader
@pytest.fixture(scope="session", autouse=True)
def _rename_pycares_shutdown_threads():
    """Allow pycares cleanup threads by renaming them to waitpid-* (per plugin rules)."""

    monkeypatch = MonkeyPatch()
    original_init = threading.Thread.__init__

    @wraps(original_init)
    def patched_init(
        self,
        group=None,
        target=None,
        name=None,
        args=(),
        kwargs=None,
        *,
        daemon=None,
    ):
        original_init(
            self,
            group=group,
            target=target,
            name=name,
            args=args,
            kwargs=kwargs,
            daemon=daemon,
        )
        actual_target = target
        if actual_target and getattr(actual_target, "__name__", "") == "_run_safe_shutdown_loop":
            self.name = f"waitpid-{self.name}"

    monkeypatch.setattr(threading.Thread, "__init__", patched_init)
    yield
    monkeypatch.undo()
