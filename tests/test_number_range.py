"""Unit tests for :mod:`custom_components.dessmonitor.number_range`.

These cover the pure slider range/step logic that backs the charging-voltage
and current number entities. The behaviour exists because the DessMonitor API
sometimes returns a wrong or missing ``hint`` for a control:

* issue #23 - a missing hint left the step at HA's coarse default of ``1`` and
  the range at ``0-100``.
* issue #22 - a wrong hint (e.g. ``25-30V`` on a 48V system reading ``57.6V``)
  made the slider unusable and rejected valid ``number.set_value`` calls.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.number_range import (
    compute_range_and_step,
    is_hint_range_usable,
    parse_hint_range,
)


class TestParseHintRange:
    """Parsing the API ``hint`` string into a (min, max) pair."""

    @pytest.mark.parametrize(
        ("hint", "expected"),
        [
            ("48.0~56.0V", (48.0, 56.0)),
            ("60.0~66V", (60.0, 66.0)),
            ("0-900min", (0.0, 900.0)),
            ("66~60V", (60.0, 66.0)),  # reversed bounds are normalised
            ("0.5~1.5", (0.5, 1.5)),
            (" -10 — 10A ", (-10.0, 10.0)),
        ],
    )
    def test_valid_ranges(self, hint: str, expected: tuple[float, float]) -> None:
        assert parse_hint_range(hint) == expected

    @pytest.mark.parametrize(
        "hint",
        [
            "48V",  # single number
            "",
            "abc",
            "no numbers here",
            "1.2.3~4.5",  # two tokens, but the first is not a valid float
            "prefix 1~2V",  # arbitrary digit fragments are not a valid hint
            "1~2V suffix",
        ],
    )
    def test_unparseable_returns_none(self, hint: str) -> None:
        assert parse_hint_range(hint) == (None, None)


class TestStep:
    """Step is derived from the unit and is always set (issue #23)."""

    @pytest.mark.parametrize(
        ("unit", "expected_step"),
        [
            ("V", 0.1),
            ("A", 0.1),
            ("min", 1.0),
            ("%", 1.0),
            ("", 1.0),
            (None, 1.0),
            ("  V  ", 0.1),  # surrounding whitespace is tolerated
        ],
    )
    def test_step_from_unit(self, unit: str | None, expected_step: float) -> None:
        assert compute_range_and_step(unit, None, None)[2] == expected_step


class TestTrustsGoodHint:
    """A complete hint that brackets the live value is used verbatim."""

    def test_hint_with_value_inside(self) -> None:
        assert compute_range_and_step("V", "48.0~56.0V", 54.0) == (48.0, 56.0, 0.1)

    def test_hint_without_value(self) -> None:
        assert compute_range_and_step("V", "48.0~56.0V", None) == (48.0, 56.0, 0.1)

    @pytest.mark.parametrize("value", [48.0, 56.0])
    def test_value_on_boundary_is_inside(self, value: float) -> None:
        assert compute_range_and_step("V", "48.0~56.0V", value) == (48.0, 56.0, 0.1)

    def test_hint_usability(self) -> None:
        assert is_hint_range_usable("48.0~56.0V", 54.0)
        assert not is_hint_range_usable("48.0~56.0V", 57.6)
        assert not is_hint_range_usable(None, 54.0)


class TestWrongHint:
    """Issue #22: an inconsistent hint is replaced by a safe fallback."""

    def test_hint_below_value_is_widened(self) -> None:
        # 48V system reads 57.6V but the API claims a 25-30V range.
        lo, hi, step = compute_range_and_step("V", "25~30V", 57.6)
        assert lo <= 57.6 <= hi
        assert (lo, hi, step) == pytest.approx((0.0, 100.0, 0.1))

    def test_hint_above_value_is_widened(self) -> None:
        # A 12V system reads 13.8V but the API claims a 60-66V range.
        lo, hi, step = compute_range_and_step("V", "60~66V", 13.8)
        assert lo <= 13.8 <= hi
        assert (lo, hi, step) == pytest.approx((0.0, 100.0, 0.1))

    def test_widened_range_admits_the_live_value(self) -> None:
        # The whole point: the device's own setting must be settable again.
        lo, hi, _ = compute_range_and_step("A", "5~10A", 80.0)
        assert lo <= 80.0 <= hi


class TestMissingHint:
    """Issue #23: no hint, so a usable range is synthesized."""

    def test_voltage_uses_stable_fallback(self) -> None:
        assert compute_range_and_step("V", None, 54.0) == (0.0, 100.0, 0.1)

    def test_current_uses_stable_fallback(self) -> None:
        assert compute_range_and_step("A", None, 40.0) == (0.0, 200.0, 0.1)

    def test_current_range_is_not_derived_from_startup_value(self) -> None:
        """Issue #30: a cached 9 A must not produce a moving 4-14 A range."""
        lo, hi, step = compute_range_and_step("A", None, 9.0)
        assert (lo, hi, step) == (0.0, 200.0, 0.1)
        assert lo <= 5.0 <= 80.0 <= hi

    def test_large_live_value_widens_stable_fallback(self) -> None:
        assert compute_range_and_step("A", None, 200.0) == (0.0, 300.0, 0.1)

    def test_lower_bound_floored_at_zero(self) -> None:
        lo, _, _ = compute_range_and_step("V", None, 5.0)
        assert lo == 0.0

    @pytest.mark.parametrize("unit", ["V", "A"])
    def test_no_hint_no_value_uses_unit_default(self, unit: str) -> None:
        expected_max = 100.0 if unit == "V" else 200.0
        assert compute_range_and_step(unit, None, None) == (0.0, expected_max, 0.1)

    def test_tiny_value_keeps_a_usable_span(self) -> None:
        # A minimum span prevents a degenerate zero-width slider.
        lo, hi, _ = compute_range_and_step("V", None, 0.0)
        assert hi - lo >= 5.0


class TestNonVoltAmpUnitsAreConservative:
    """For units other than V/A a range is never invented, only widened."""

    def test_no_hint_no_range_synthesized(self) -> None:
        # Leave HA's defaults rather than guess a magnitude for e.g. a timer.
        assert compute_range_and_step("min", None, 30.0) == (None, None, 1.0)

    def test_good_hint_is_trusted(self) -> None:
        assert compute_range_and_step("min", "0~900min", 300.0) == (0.0, 900.0, 1.0)

    def test_hint_widened_up_to_value(self) -> None:
        assert compute_range_and_step("min", "0~100min", 300.0) == (0.0, 300.0, 1.0)

    def test_hint_widened_down_to_value(self) -> None:
        assert compute_range_and_step("min", "500~900min", 300.0) == (300.0, 900.0, 1.0)


class TestNoRegressionOnStep:
    """Whatever the range path, V/A keep the fine 0.1 step (issue #23)."""

    @pytest.mark.parametrize(
        ("unit", "hint", "value"),
        [
            ("V", None, None),
            ("V", None, 54.0),
            ("V", "48~56V", 54.0),
            ("V", "25~30V", 57.6),
            ("A", None, 40.0),
        ],
    )
    def test_volt_amp_step_is_fine(
        self, unit: str, hint: str | None, value: float | None
    ) -> None:
        assert compute_range_and_step(unit, hint, value)[2] == 0.1
