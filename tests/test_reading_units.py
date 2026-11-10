"""Scaling a reading whose collector and sensor disagree about the unit.

An entity's unit comes from ``SENSOR_TYPES`` and never from the payload, so a
collector reporting watt-hours on a reading published in kilowatt-hours puts a
figure a thousand times too large on the energy dashboard and into long-term
statistics. Devcode 2449 did exactly that with both generation counters (#71),
and devcode 2452 had the same defect with a hand-written callback correcting
it for that devcode alone.

These tests pin the decision to the unit the collector declares, which is the
only thing that distinguishes the two cases, and pin the case that matters most
for the installations already running: a collector that already reports the
canonical unit is left alone.
"""

from __future__ import annotations

from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
)


def _reading(title: str, val: object, unit: str) -> dict[str, object]:
    return {"title": title, "val": val, "unit": unit}


def test_watt_hours_reach_a_kilowatt_hour_sensor_scaled() -> None:
    """The lifetime counter from #71, as the reporter's two inverters sent it."""
    point = apply_devcode_transformations(
        2449, _reading("Total generation", "15045200", "Wh")
    )

    assert point["title"] == "Energy Total"
    assert point["val"] == 15045.2
    assert point["unit"] == "kWh"


def test_the_daily_counter_is_scaled_too() -> None:
    point = apply_devcode_transformations(
        2449, _reading("Today generation", "8466", "Wh")
    )

    assert point["val"] == 8.466


def test_a_collector_reporting_the_canonical_unit_is_untouched() -> None:
    """The guard for every installation that is already correct.

    A per-title conversion scales whatever it is given, so it would divide
    this reading by a thousand and break an install that works today.
    """
    point = apply_devcode_transformations(
        2449, _reading("Total generation", "15045.2", "kWh")
    )

    assert point["val"] == "15045.2"
    assert point["unit"] == "kWh"


def test_a_declared_source_unit_covers_a_payload_that_omits_one() -> None:
    """A profile states what the committed download showed."""
    point = apply_devcode_transformations(
        2449, _reading("Today generation", "8466", "")
    )

    assert point["val"] == 8.466


def test_devcode_2452_still_scales_its_daily_counter() -> None:
    """Replacing its callback must not change what that devcode publishes.

    Its committed download labels Today, Month and Year generation "Wh" and
    reports the lifetime total in kWh already.
    """
    today = apply_devcode_transformations(
        2452, _reading("Today generation", "11762", "Wh")
    )
    year = apply_devcode_transformations(
        2452, _reading("Year generation", "4370034", "Wh")
    )

    assert today["title"] == "Energy Today"
    assert today["val"] == 11.762
    assert year["val"] == 4370.034


def test_devcode_2452_leaves_a_lifetime_total_already_in_kilowatt_hours() -> None:
    point = apply_devcode_transformations(
        2452, _reading("Energy Total", "10104.399", "kWh")
    )

    assert point["val"] == "10104.399"


def test_a_devcode_with_no_profile_is_scaled_from_its_own_label() -> None:
    """The vendor's label is the evidence, so no profile is needed for it.

    Devcode 2548 in #67 reports "battery energy today discharge" in Wh.
    """
    point = apply_devcode_transformations(
        999999, _reading("Energy Today", "1447.6", "Wh")
    )

    assert point["val"] == 1.4476


def test_a_reading_with_no_canonical_sensor_is_left_alone() -> None:
    point = apply_devcode_transformations(
        2449, _reading("Cumulative charging capacity of mains", "54962", "Wh")
    )

    assert point["val"] == "54962"


def test_a_non_numeric_value_is_not_scaled() -> None:
    """Fail quiet here, not loud: the support report still records the row."""
    point = apply_devcode_transformations(
        2449, _reading("Total generation", "--", "Wh")
    )

    assert point["val"] == "--"


def test_an_unlisted_unit_pair_is_left_alone() -> None:
    """The table holds only pairs a committed download shows.

    A scale nobody has measured is a thousand-fold error waiting for the
    devcode that does not need it.
    """
    point = apply_devcode_transformations(
        2449, _reading("Total generation", "15.0452", "MWh")
    )

    assert point["val"] == "15.0452"
    assert point["unit"] == "MWh"


def test_a_scale_is_reported_once_per_reading(caplog) -> None:
    """The only trace a conversion leaves, and a hot path, so once per reading.

    A download records the converted value against the sensor's own unit, so
    it cannot show that a conversion happened. If a collector ever labels a
    reading Wh while sending kilowatt-hours, this line names which reading was
    divided and what decided it.
    """
    import logging

    from custom_components.dessmonitor.device_support import device_registry

    device_registry._REPORTED_SCALES.clear()
    with caplog.at_level(
        logging.DEBUG, logger="custom_components.dessmonitor.device_support"
    ):
        for _ in range(3):
            apply_devcode_transformations(
                2449, _reading("Total generation", "15045200", "Wh")
            )

    scaled = [record for record in caplog.records if "are scaled by" in record.message]
    assert len(scaled) == 1
    assert "Energy Total" in scaled[0].getMessage()
    assert "Wh" in scaled[0].getMessage()
