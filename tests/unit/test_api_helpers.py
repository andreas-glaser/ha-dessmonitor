"""Tests for small helpers in the API client."""

import pytest

from custom_components.dessmonitor.api import _mask_identifier, DessMonitorAPI
from tests.common import FakeStore


def test_mask_identifier_redacts_long_values():
    assert _mask_identifier("username@example.com") == "use***"
    assert _mask_identifier("abc") == "***"
    assert _mask_identifier("") == "***"


@pytest.mark.asyncio
async def test_build_action_string_orders_params():
    api = DessMonitorAPI(
        username="user",
        password="pass",
        company_key="key",
        store=FakeStore(),
    )

    result = api._build_action_string("query", {"a": 1, "b": 2})
    assert result == "&action=query&a=1&b=2"
    await api.close()
