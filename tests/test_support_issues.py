"""The Repairs card that answers "is my inverter supported" in the UI (#60).

The existing answer was one log line, warned once per devcode until a restart,
and the partial case warned nothing: devcode 6514 shipped mapping SOC alone and
dropped 58 of its 76 readings for eight months (#35, then #56).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator
from custom_components.dessmonitor.const import DOMAIN

UNSUPPORTED_DEVCODE = 9999


def _payload(devcode: int, readings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "collector": {"pn": "PN-1"},
        "device": {"devcode": devcode, "devaddr": 1, "alias": "Solar"},
        "data": readings,
    }


def _coordinator(hass: HomeAssistant) -> DessMonitorDataUpdateCoordinator:
    coordinator = DessMonitorDataUpdateCoordinator(hass, AsyncMock(), 300)
    coordinator.config_entry = MagicMock(entry_id="entry-1")
    return coordinator


def _issue(hass: HomeAssistant, devcode: int) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"devcode_support_{devcode}")


async def test_an_unsupported_devcode_raises_a_card(hass: HomeAssistant) -> None:
    coordinator = _coordinator(hass)

    coordinator._async_update_support_issues(
        {"SN-1": _payload(UNSUPPORTED_DEVCODE, [{"title": "Whatever", "val": "1"}])}
    )

    issue = _issue(hass, UNSUPPORTED_DEVCODE)
    assert issue is not None
    assert issue.translation_key == "devcode_unsupported"
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["devcode"] == str(UNSUPPORTED_DEVCODE)
    assert issue.learn_more_url and "ADDING_DEVCODES" in issue.learn_more_url


async def test_a_profile_that_drops_a_reading_raises_the_partial_card(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator(hass)

    coordinator._async_update_support_issues(
        {
            "SN-1": _payload(
                6515,
                [
                    {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
                    {"title": "Daily Generation", "val": "10.2", "unit": "kWh"},
                ],
            )
        }
    )

    issue = _issue(hass, 6515)
    assert issue is not None
    assert issue.translation_key == "devcode_partial"
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["dropped"] == "1"
    assert issue.translation_placeholders["resolved"] == "1"
    assert issue.translation_placeholders["total"] == "2"


async def test_a_fully_mapped_devcode_raises_nothing(hass: HomeAssistant) -> None:
    coordinator = _coordinator(hass)

    coordinator._async_update_support_issues(
        {"SN-1": _payload(6515, [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}])}
    )

    assert _issue(hass, 6515) is None


async def test_the_card_is_withdrawn_once_it_stops_applying(
    hass: HomeAssistant,
) -> None:
    """A profile added in an update must clear the card it was raised for."""
    coordinator = _coordinator(hass)
    dropping = {
        "SN-1": _payload(
            6515,
            [
                {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
                {"title": "Daily Generation", "val": "10.2", "unit": "kWh"},
            ],
        )
    }

    coordinator._async_update_support_issues(dropping)
    assert _issue(hass, 6515) is not None

    coordinator._async_update_support_issues(
        {"SN-1": _payload(6515, [{"title": "Battery Voltage", "val": "53.1", "unit": "V"}])}
    )
    assert _issue(hass, 6515) is None


async def test_one_card_per_devcode_not_per_device(hass: HomeAssistant) -> None:
    """Five inverters of one model must not raise five identical cards."""
    coordinator = _coordinator(hass)
    readings = [{"title": "Whatever", "val": "1"}]

    coordinator._async_update_support_issues(
        {
            f"SN-{index}": _payload(UNSUPPORTED_DEVCODE, readings)
            for index in range(5)
        }
    )

    assert len(ir.async_get(hass).issues) == 1


async def test_the_worst_status_wins_for_one_devcode(hass: HomeAssistant) -> None:
    """Two devices of one devcode, one of which drops readings."""
    coordinator = _coordinator(hass)

    coordinator._async_update_support_issues(
        {
            "SN-1": _payload(
                UNSUPPORTED_DEVCODE, [{"title": "A", "val": "1", "unit": "W"}]
            ),
            "SN-2": _payload(UNSUPPORTED_DEVCODE, [{"title": "B", "val": "2"}]),
        }
    )

    issue = _issue(hass, UNSUPPORTED_DEVCODE)
    assert issue is not None
    assert issue.translation_key == "devcode_unsupported"


async def test_a_device_without_a_usable_devcode_is_skipped(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator(hass)

    coordinator._async_update_support_issues(
        {
            "SN-1": {
                "collector": {"pn": "PN-1"},
                "device": {"devaddr": 1, "alias": "Solar"},
                "data": [{"title": "Whatever", "val": "1"}],
            }
        }
    )

    assert not ir.async_get(hass).issues


async def test_the_evaluation_does_not_advance_the_revision(
    hass: HomeAssistant,
) -> None:
    """Entity discovery retries on cloud_revision; a card must not trigger it."""
    coordinator = _coordinator(hass)
    coordinator.cloud_revision = 4

    coordinator._async_update_support_issues(
        {"SN-1": _payload(UNSUPPORTED_DEVCODE, [{"title": "Whatever", "val": "1"}])}
    )

    assert coordinator.cloud_revision == 4


async def test_a_successful_refresh_evaluates_support(hass: HomeAssistant) -> None:
    """It runs on the refresh path, not on a local push."""
    coordinator = _coordinator(hass)
    data = {"SN-1": _payload(UNSUPPORTED_DEVCODE, [{"title": "Whatever", "val": "1"}])}

    with (
        patch.object(coordinator, "_fetch_collectors", AsyncMock(return_value=[])),
        patch.object(
            coordinator, "_gather_all_device_data", AsyncMock(return_value=data)
        ),
        patch.object(coordinator, "_merge_summary_data", AsyncMock()),
        patch.object(coordinator, "_async_store_cloud_snapshot", AsyncMock()),
    ):
        await coordinator._async_update_data()

    assert _issue(hass, UNSUPPORTED_DEVCODE) is not None
    await coordinator.async_shutdown()


@pytest.mark.parametrize("entry", [None])
async def test_an_entry_less_coordinator_raises_nothing(
    hass: HomeAssistant, entry: None
) -> None:
    """Guards the test-constructed coordinator, which has no config entry."""
    coordinator = DessMonitorDataUpdateCoordinator(hass, AsyncMock(), 300)
    coordinator.config_entry = entry

    coordinator._async_update_support_issues(
        {"SN-1": _payload(UNSUPPORTED_DEVCODE, [{"title": "Whatever", "val": "1"}])}
    )

    assert not ir.async_get(hass).issues
