"""The values a collector has been seen to send (#63, item 2).

A download records whichever value was current when it was taken, and the
mapping tables - OPERATING_MODE_MAPPING and the two priority tables - are
written from the set of values a collector emits. A CLI analysis collected a
few of them and the download collected none, so every reporter moved from the
CLI to the download gave us less of what that work depends on. The integration
polls continuously, so this is the one thing it can report that no snapshot
can.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.support_report import (
    OBSERVED_VALUES_PER_READING,
    build_support_report,
    is_enum_shaped_value,
    record_observed_values,
    report_checksum,
    unmapped_state_words,
)


def _reading(title: str, value: object) -> dict[str, object]:
    return {"title": title, "val": value, "unit": ""}


def test_a_repeated_value_is_recorded_once_and_counted() -> None:
    store: dict[str, dict[str, object]] = {}
    for _ in range(5):
        record_observed_values(store, [_reading("Operating mode", "Mains Mode")])

    assert store["Operating mode"]["values"] == ["Mains Mode"]
    assert store["Operating mode"]["observations"] == 5
    assert store["Operating mode"]["truncated"] is False


def test_every_distinct_value_is_kept_in_the_order_seen() -> None:
    """The set is the point: a mode seen once at dawn is still a mode."""
    store: dict[str, dict[str, object]] = {}
    for mode in ("Mains Mode", "Battery Mode", "Mains Mode", "Fault Mode"):
        record_observed_values(store, [_reading("Operating mode", mode)])

    assert store["Operating mode"]["values"] == [
        "Mains Mode",
        "Battery Mode",
        "Fault Mode",
    ]


def test_the_cap_is_recorded_rather_than_rotated() -> None:
    """The first values are the ones a mapping is written from.

    A reading that overflows the cap is reporting something other than a
    state, and the flag is what says so in the file.
    """
    store: dict[str, dict[str, object]] = {}
    for index in range(OBSERVED_VALUES_PER_READING + 6):
        record_observed_values(store, [_reading("Fault word", f"word {index}")])

    record = store["Fault word"]
    assert len(record["values"]) == OBSERVED_VALUES_PER_READING
    assert record["values"][0] == "word 0"
    assert record["truncated"] is True
    assert record["observations"] == OBSERVED_VALUES_PER_READING + 6


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Mains Mode", True),
        ("Solar first", True),
        ("OFF", True),
        ("V106.014.000", True),
        ("53.1", False),
        ("0", False),
        ("-1.5", False),
        ("", False),
        ("   ", False),
        (None, False),
        (53.1, False),
        # A clock or a date fills the cap with twelve strings inside twelve
        # minutes and evicts the state words the cap exists to hold.
        ("2026-11-19 17:10:02", False),
        ("16:32", False),
        ("x" * 65, False),
    ],
)
def test_only_a_state_word_is_collected(value: object, expected: bool) -> None:
    assert is_enum_shaped_value(value) is expected


def test_a_number_is_never_collected_as_a_state() -> None:
    """A number collected as a state is how an enum ends up with 100 options."""
    store: dict[str, dict[str, object]] = {}
    record_observed_values(store, [_reading("Battery Voltage", "53.1")])

    assert store == {}


def test_an_identifier_and_the_timestamp_are_not_collected() -> None:
    store: dict[str, dict[str, object]] = {}
    record_observed_values(
        store,
        [
            _reading("Devise serial number", "SN-0001-REPORTER"),
            _reading("Device e-SN", "ESN-0001"),
            _reading("Timestamp", "a moment ago"),
            _reading("Inverter status", "standby mode"),
        ],
    )

    assert list(store) == ["Inverter status"]


def test_the_number_of_readings_collected_for_is_bounded() -> None:
    store: dict[str, dict[str, object]] = {}
    record_observed_values(
        store, [_reading(f"Reading {index}", "a word") for index in range(500)]
    )

    assert len(store) == 128


def test_the_report_carries_them_sorted_and_inside_the_checksum() -> None:
    report = build_support_report(
        devcode=6515,
        readings=[_reading("Operating mode", "Mains Mode")],
        observed_values={
            "Operating mode": {
                "values": ["Mains Mode", "Battery Mode"],
                "observations": 288,
                "truncated": False,
            },
            "Inverter status": {
                "values": ["Normal"],
                "observations": 288,
                "truncated": False,
            },
        },
    )

    assert list(report["observed_values"]) == ["Inverter status", "Operating mode"]
    assert report["checksum"] == report_checksum(report)


def test_the_section_is_absent_when_nothing_was_collected() -> None:
    report = build_support_report(devcode=6515, readings=[], observed_values={})

    assert "observed_values" not in report


def test_a_state_word_its_enum_would_reject_is_named() -> None:
    """The defect this section exists to make visible before an owner does.

    An enum sensor discards a value its option list does not offer, so the
    sensor reads Unknown and nothing says why.
    """
    report = build_support_report(
        devcode=6515,
        readings=[],
        observed_values={
            "Operating mode": {
                "values": ["Mains Mode", "Hybrid grid-feeding"],
                "observations": 12,
                "truncated": False,
            }
        },
    )

    assert unmapped_state_words(report) == {
        "Operating mode": ["Hybrid grid-feeding"]
    }


def test_a_value_the_profile_already_translates_is_not_a_gap() -> None:
    """The devcode's own mapping runs first, because the entity reads it."""
    report = build_support_report(
        devcode=684,
        readings=[],
        observed_values={
            "work mode": {
                "values": ["normal"],
                "observations": 12,
                "truncated": False,
            }
        },
    )

    assert unmapped_state_words(report) == {}


def test_a_text_sensor_is_not_judged_against_an_option_list() -> None:
    """Only an enum rejects a value; a text sensor publishes whatever came."""
    report = build_support_report(
        devcode=6515,
        readings=[],
        observed_values={
            "Inverter Status": {
                "values": ["Battery Discharge", "Load On (Normal)"],
                "observations": 12,
                "truncated": False,
            }
        },
    )

    assert unmapped_state_words(report) == {}


async def test_the_coordinator_collects_them_across_refreshes(hass) -> None:
    """The whole point of item 2: the set accumulates where a snapshot cannot.

    Two refreshes, two different modes, and the file carries both - which is
    what a mapping is written from and what one download can never show.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator

    api = MagicMock()
    api.close = AsyncMock()
    coordinator = DessMonitorDataUpdateCoordinator(hass, api, 300)
    coordinator.async_get_controls_with_values = AsyncMock()

    def payload(mode: str) -> dict[str, object]:
        return {
            "DEVICE": {
                "collector": {"pn": "COLLECTOR"},
                "device": {"devcode": 6515, "devaddr": 1},
                "data": [
                    {"title": "Operating mode", "val": mode, "unit": ""},
                    {"title": "Battery Voltage", "val": "53.1", "unit": "V"},
                ],
            }
        }

    try:
        for mode in ("Mains Mode", "Battery Mode", "Mains Mode"):
            with (
                patch.object(
                    coordinator, "_fetch_collectors", AsyncMock(return_value=[])
                ),
                patch.object(
                    coordinator,
                    "_gather_all_device_data",
                    AsyncMock(return_value=payload(mode)),
                ),
                patch.object(coordinator, "_merge_summary_data", AsyncMock()),
                patch.object(
                    coordinator, "_async_store_cloud_snapshot", AsyncMock()
                ),
            ):
                await coordinator._async_update_data()
    finally:
        await coordinator.async_shutdown()

    collected = coordinator.observed_reading_values["DEVICE"]
    assert collected["Operating mode"]["values"] == ["Mains Mode", "Battery Mode"]
    assert collected["Operating mode"]["observations"] == 3
    assert "Battery Voltage" not in collected


async def test_no_configured_value_is_collected_as_a_state_word(hass) -> None:
    """The redaction promise has to grow with each new section (#63).

    This section records values a collector sent, and a collector can repeat
    anything - a serial, an alias, a WiFi SSID. Identifying titles are
    excluded by name; this asserts the categorical claim instead of trusting
    the list.
    """
    from custom_components.dessmonitor.support_report import is_identifier_name

    identifying = [
        "Devise serial number",
        "Device e-SN",
        "device sn",
        "collector alias",
        "Collector product number",
        "MAC address",
        "IP address",
        "WiFi SSID",
        "token",
    ]
    assert all(is_identifier_name(title) for title in identifying)

    store: dict[str, dict[str, object]] = {}
    record_observed_values(
        store, [_reading(title, "sentinel-9f3b") for title in identifying]
    )

    assert store == {}
