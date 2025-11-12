"""Shared test utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> str:
    """Return the raw contents of a fixture file."""
    path = FIXTURES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Fixture {filename} not found in {FIXTURES_DIR}")
    return path.read_text(encoding="utf-8")


def load_json_fixture(filename: str) -> Any:
    """Return the parsed JSON content of a fixture file."""
    return json.loads(load_fixture(filename))


class FakeStore:
    """Minimal in-memory replacement for Home Assistant's Store helper."""

    def __init__(self) -> None:
        self.data: Any = None

    async def async_load(self) -> Any:
        return self.data

    async def async_save(self, data: Any) -> None:
        self.data = data

    # Backwards compatibility for old style calls in repositories
    async def load(self) -> Any:  # pragma: no cover - compatibility shim
        return await self.async_load()

    async def save(self, data: Any) -> None:  # pragma: no cover - compatibility shim
        await self.async_save(data)
