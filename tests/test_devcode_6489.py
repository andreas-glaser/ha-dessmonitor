"""Devcode 6489, the JSD Solar hybrid reported in #66.

The reporter's diagnostics download resolved 21 of 71 titles and dropped 40
that carry a unit, which is the shape a devcode has before anyone works
through its telemetry. These tests pin the decisions that profile makes:
which readings become which sensor, which titles are settings rather than
readings, and which of the collector's duplicated fields wins.

Evidence is ``docs/evidence/devcodes/analysis_6489.json``.
"""

from __future__ import annotations

import pytest

from custom_components.dessmonitor.const import SENSOR_TYPES
from custom_components.dessmonitor.device_support import (
    apply_devcode_transformations,
    is_devcode_supported,
    is_setting_reading,
    map_operating_mode,
)
from custom_components.dessmonitor.sensor_titles import resolve_sensor_key

DEVCODE = 6489


def _resolved_key(title: str) -> str | None:
    """Return the sensor key a raw title reaches through this devcode."""
    mapped = apply_devcode_transformations(DEVCODE, {"title": title, "val": "1"})
    return resolve_sensor_key(mapped.get("title"), title)


def test_the_devcode_is_registered() -> None:
    assert is_devcode_supported(DEVCODE) is True


@pytest.mark.parametrize(
    "title,expected_key",
    [
        # Mains section. The parameters endpoint names the voltage
        # gd_grid_voltage, which is what places it.
        ("Mains input voltage", "Grid Voltage"),
        ("Mains frequency", "Grid Frequency"),
        ("Total electricity consumption of the day", "Daily Mains Load Energy"),
        ("Total electricity consumption", "Accumulated Mains Load Energy"),
        # Battery section: measurements, not the setpoints beside them.
        ("Charging voltage", "Battery Charging Voltage"),
        ("Charging current", "Battery Charging Current"),
        # AC output section.
        ("output half wave apparent power", "Output Half Wave Apparent Power"),
        ("Output current percentage", "Output Current Percentage"),
        (
            "Output the total electricity consumption of the day",
            "Daily Load Energy",
        ),
        ("Total output electricity consumption", "Accumulated Load Power"),
        # PV section, which is the account's generation.
        ("Total PV power generation on the day", "Energy Today"),
        ("Total photovoltaic power generation", "Energy Total"),
        # The summary endpoint's spellings of the same two figures.
        ("energyToday", "Energy Today"),
        ("energyTotal", "Energy Total"),
        # BMS section.
        ("BMS voltage", "BMS battery voltage"),
        ("BMS current", "BMS battery current"),
        ("BMS Temperature", "BMS battery temperature"),
        ("BMS SOC", "State of Charge"),
        ("BMS Remaining power", "BMS Remaining Capacity"),
        ("BMS Rating Energy", "BMS Rated Capacity"),
        ("BMS max change current", "BMS Max Charge Current"),
        ("BMS cv point voltage", "BMS CV Point Voltage"),
        # Cooling and the charger's own stage.
        ("Fan speed", "Fan Speed"),
        ("Charge Mode", "Charge Mode"),
    ],
)
def test_readings_reach_their_sensor(title: str, expected_key: str) -> None:
    assert _resolved_key(title) == expected_key


def test_the_dashboard_block_does_not_take_a_sensor_from_the_detailed_one() -> None:
    """This collector repeats readings, and a duplicate must not split a sensor.

    It leads with a short dashboard block and then reports the measurements
    again in full sections. ``Output voltage`` arrives in both, which is what
    establishes the duplication, and ``Input frequency`` is the dashboard copy
    of ``Mains frequency``: both read 0.00 with the mains absent. They have to
    land on one key, or the collector's two spellings would publish two
    entities for one reading, as the two spellings of Grid Frequency did on
    devcode 2452 (#53).
    """
    assert _resolved_key("Input frequency") == _resolved_key("Mains frequency")


def test_the_one_dashboard_field_with_no_counterpart_is_the_rating() -> None:
    """``frequency`` reads the nominal 50.0 beside ``Rated voltage`` 230.0.

    The measured output and inverter frequencies read 49.90 and 49.97 in the
    same download, so this is not a third measurement of either.
    """
    key = _resolved_key("frequency")

    assert key == "rated frequency"
    assert SENSOR_TYPES[key]["entity_category"] == "diagnostic"


@pytest.mark.parametrize(
    "title",
    [
        # The one that is also a control the account publishes.
        "Maximum charging current",
        # The grid-protection window.
        "High point of mains loss voltage",
        "Low point of mains loss voltage",
        "Mains loss voltage high recovery point",
        "Mains loss voltage low recovery point",
        "High frequency of mains loss",
        "Low frequency of mains loss",
        # The charger profile and the battery's protection setpoints.
        "Battery discharge alarm voltage",
        "Battery discharge cut-off voltage",
        "Constant voltage charging voltage",
        "Float charging voltage",
        "Equalization charging voltage",
        "Constant voltage charging time",
        "Equalization charging time",
        "Equalization Charge Timeout",
        "Equalization charging interval",
        "Low power discharge time",
        "Balanced charging mode",
        "Battery Type",
        "Number of battery cells",
    ],
)
def test_setpoints_are_declared_settings_rather_than_sensors(title: str) -> None:
    """A setting is not a reading whichever way the vendor delivers it."""
    assert is_setting_reading(DEVCODE, title) is True
    assert _resolved_key(title) is None


def test_a_measurement_beside_the_setpoints_is_not_declared_a_setting() -> None:
    """The charger reports its live voltage and current next to its setpoints.

    Both read 0.0 in the download while Charge Mode reads "Stop charging" and
    the CV, float and equalization setpoints read 56.4, 55.2 and 58.4 V.
    Declaring either a setting would take away a sensor.
    """
    assert is_setting_reading(DEVCODE, "Charging voltage") is False
    assert is_setting_reading(DEVCODE, "Charging current") is False
    assert is_setting_reading(DEVCODE, "Battery voltage") is False


def test_the_observed_operating_mode_is_canonical() -> None:
    """Only the one mode the download observed is registered.

    Any value this collector emits that no mapping knows reads as unavailable,
    so registering a guess at the vendor's wording would not help; the rest
    wait on a download taken with the mains present.
    """
    assert map_operating_mode(DEVCODE, "Battery mode") == "Battery"


def test_the_new_sensor_keys_publish_one_entity_name_each() -> None:
    """Two keys with one display name give a device two entities called it.

    That is how an Energy Today sensor fed by a field the vendor left unset
    read 0 kWh beside a working one (#58), and the keys added for this devcode
    double the places it could happen.
    """
    added = {
        "Output Current Percentage",
        "Battery Charging Voltage",
        "Output Half Wave Apparent Power",
        "Fan Speed",
        "Daily Mains Load Energy",
        "Daily Load Energy",
        "Charge Mode",
        "BMS Remaining Capacity",
        "BMS Rated Capacity",
        "BMS Max Charge Current",
        "BMS CV Point Voltage",
    }

    for key in added:
        assert key in SENSOR_TYPES, f"{key} is not a sensor type"
        name = SENSOR_TYPES[key]["name"]
        clashes = sorted(
            other
            for other, config in SENSOR_TYPES.items()
            if other != key and config["name"] == name
        )
        assert not clashes, f"{key} publishes the same name as {clashes}"


def _committed_readings() -> list[dict[str, str]]:
    """The reporter's own readings, as the committed download records them."""
    import json
    from pathlib import Path

    from custom_components.dessmonitor.support_report import normalized_reports

    path = (
        Path(__file__).resolve().parent.parent
        / "docs/evidence/devcodes/analysis_6489.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    (device,) = payload["data"]["devices"]
    return [
        {
            "title": reading["title"],
            "val": reading.get("value", ""),
            "unit": reading.get("unit", ""),
        }
        for reading in device["readings"]
    ]


def test_the_reporter_s_device_reads_as_supported() -> None:
    """A unit-carrying reading that reaches no entity makes this partial.

    The download this profile was written from had forty of them, which is
    what raised the Repairs card the reporter attached it to.
    """
    from custom_components.dessmonitor.support_report import device_support_status

    support = device_support_status(DEVCODE, _committed_readings())

    assert support["status"] == "supported"
    assert support["unresolved_with_unit"] == []
    assert support["excluded"]["declared_settings"] == 20


def test_the_reporter_s_device_publishes_one_entity_per_reading(hass) -> None:
    """Build the entities this device would get, from its own payload.

    No hardware here answers this devcode, so the published entity set is
    checked against the reporter's download instead: every unique id and every
    display name distinct, which is what a duplicated reading or a key that
    shares a name with another would break.
    """
    from unittest.mock import MagicMock

    from custom_components.dessmonitor.sensor import _build_sensor_entities

    coordinator = MagicMock(
        hass=hass,
        data={
            "SN-6489": {
                "collector": {"pn": "PN-1"},
                "device": {"devcode": DEVCODE, "alias": "Home"},
                "data": _committed_readings(),
            }
        },
    )

    entities = _build_sensor_entities(coordinator, set())

    unique_ids = [entity.unique_id for entity in entities]
    names = [entity.name for entity in entities]
    assert len(set(unique_ids)) == len(unique_ids), "a device got two of one entity"
    assert len(set(names)) == len(names), f"two entities share a name: {sorted(names)}"
    # The duplicated readings land on one sensor each, not two.
    assert unique_ids.count("SN-6489_grid_frequency") == 1
    assert unique_ids.count("SN-6489_output_voltage") == 1
    # And the readings this profile was written to recover are published.
    for unique_id in (
        "SN-6489_grid_voltage",
        "SN-6489_state_of_charge",
        "SN-6489_energy_today",
        "SN-6489_energy_total",
        "SN-6489_accumulated_load_power",
        "SN-6489_daily_mains_load_energy",
        "SN-6489_battery_charging_current",
        "SN-6489_bms_battery_voltage",
        "SN-6489_fan_speed",
        "SN-6489_charge_mode",
    ):
        assert unique_id in unique_ids, f"{unique_id} is not published"
