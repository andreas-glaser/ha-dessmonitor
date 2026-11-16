"""Local settings as Home Assistant entities, end to end.

The template a local device publishes is the cloud control template's own
shape, so these build the real number and select entities from a running local
coordinator and write through them over the real collector transport. If the
shape were wrong, it would be wrong here rather than on someone's inverter.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.components.number import NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from custom_components.dessmonitor.control_values import TRANSPORT_LOCAL
from custom_components.dessmonitor.number import _async_build_number_entities
from custom_components.dessmonitor.select import _async_build_select_entities
from tests.local.test_local_control import SERIAL, _started
from tests.local.test_coordinator import _wait_until

pytestmark = pytest.mark.usefixtures("socket_enabled")


async def _entities(coordinator):
    """Build both control platforms the way Home Assistant builds them."""
    numbers = await _async_build_number_entities(coordinator, set())
    selects = await _async_build_select_entities(coordinator, set())
    return (
        {entity._param_name: entity for entity in numbers},
        {entity._param_name: entity for entity in selects},
    )


async def test_a_read_only_entry_publishes_no_control_entity(
    hass: HomeAssistant,
) -> None:
    """Nothing is added to an installation that did not ask for it.

    The platforms are forwarded for every local entry so that loading and
    unloading stay symmetric when the option changes, and they build nothing
    at all while it is off.
    """
    coordinator, collector = await _started(hass, control=False)
    try:
        numbers, selects = await _entities(coordinator)
        assert numbers == {}
        assert selects == {}
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_the_setpoints_become_numbers_with_the_inverters_own_range(
    hass: HomeAssistant,
) -> None:
    """The range comes from the protocol and the battery class it reported.

    A cloud hint has been seen to send a 24 V range for a 48 V system (#22),
    so the number platform distrusts a hint that does not bracket the live
    value. This hint is the inverter's own documented range and brackets it,
    which is what gives these controls a usable slider instead of 0-100.
    """
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        numbers, _ = await _entities(coordinator)

        bulk = numbers["Battery Bulk Voltage"]
        assert bulk.native_value == 56.0
        assert bulk.native_unit_of_measurement == "V"
        assert (bulk.native_min_value, bulk.native_max_value) == (48.0, 58.5)
        assert bulk.native_step == 0.1
        assert bulk.mode == NumberMode.AUTO
        assert bulk.entity_category == EntityCategory.CONFIG
        assert bulk.unique_id == f"{SERIAL}_battery_bulk_voltage"
        assert bulk.extra_state_attributes["control_transport"] == "cloud"
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_the_selections_become_selects_offering_the_documented_codes(
    hass: HomeAssistant,
) -> None:
    """An option list is the protocol's codes, or the ones this unit listed."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        _, selects = await _entities(coordinator)

        priority = selects["Output Source Priority"]
        assert priority.options == [
            "Solar → Utility → Battery",
            "Solar → Battery → Utility",
        ]
        assert priority.current_option == "Solar → Battery → Utility"
        assert priority.unique_id == f"{SERIAL}_output_source_priority"

        limit = selects["Max Charging Current"]
        assert limit.current_option == "60 A"
        assert "10 A" in limit.options
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_a_write_through_the_number_entity_reaches_the_inverter(
    hass: HomeAssistant,
) -> None:
    """One click, one verified setter, and the entity shows what was confirmed."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        numbers, _ = await _entities(coordinator)
        bulk = numbers["Battery Bulk Voltage"]
        collector.commands.clear()

        with patch.object(bulk, "async_write_ha_state"):
            await bulk.async_set_native_value(57.0)

        assert "MCHGV570,540" in collector.commands
        assert bulk.native_value == 57.0
        assert bulk.extra_state_attributes["control_transport"] == TRANSPORT_LOCAL
        assert bulk.extra_state_attributes["value_status"] == "last_known"
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_a_write_through_the_select_entity_reaches_the_inverter(
    hass: HomeAssistant,
) -> None:
    """A selection is written as the code the protocol documents, not its label."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        _, selects = await _entities(coordinator)
        priority = selects["Charger Source Priority"]
        collector.commands.clear()

        with patch.object(priority, "async_write_ha_state"):
            await priority.async_select_option("Only Solar")

        assert "PCP0,2" in collector.commands
        assert priority.current_option == "Only Solar"
        assert priority.extra_state_attributes["control_transport"] == TRANSPORT_LOCAL
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_a_refused_write_leaves_the_entity_where_it_was(
    hass: HomeAssistant,
) -> None:
    """A failed write raises for the owner and never moves the displayed value."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        numbers, _ = await _entities(coordinator)
        bulk = numbers["Battery Bulk Voltage"]
        collector.ack_writes = False

        with (
            patch.object(bulk, "async_write_ha_state") as write_state,
            pytest.raises(Exception, match="was not changed"),
        ):
            await bulk.async_set_native_value(57.0)

        assert bulk.native_value == 56.0
        write_state.assert_not_called()
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_a_value_outside_the_range_never_reaches_the_inverter(
    hass: HomeAssistant,
) -> None:
    """The range is enforced before a frame is built, not by the inverter."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        numbers, _ = await _entities(coordinator)
        bulk = numbers["Battery Bulk Voltage"]
        collector.commands.clear()

        with pytest.raises(Exception, match="accepts"):
            await bulk.async_set_native_value(70.0)

        assert not [
            command for command in collector.commands if command.startswith("MCHG")
        ]
    finally:
        await collector.stop()
        await coordinator.async_shutdown()


async def test_a_panel_change_reaches_the_entity_without_a_reload(
    hass: HomeAssistant,
) -> None:
    """A setting changed on the inverter updates the entity on the next read."""
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(
            "custom_components.dessmonitor.local.coordinator"
            ".LOCAL_SETTINGS_REFRESH_CYCLES",
            1,
        )
        coordinator, collector = await _started(hass, control=True)
        try:
            await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
            numbers, _ = await _entities(coordinator)
            bulk = numbers["Battery Bulk Voltage"]
            assert bulk.native_value == 56.0

            collector.ratings[11] = "575"
            await _wait_until(
                lambda: coordinator.ctrl_value_cache[SERIAL][
                    "battery_bulk_voltage"
                ]
                == "57.5",
                timeout=8.0,
            )
            with patch.object(bulk, "async_write_ha_state"):
                bulk._handle_coordinator_update()

            assert bulk.native_value == 57.5
        finally:
            await collector.stop()
            await coordinator.async_shutdown()


async def test_a_local_entity_carries_no_cloud_identity(hass: HomeAssistant) -> None:
    """The device these controls belong to is the local inverter's own."""
    coordinator, collector = await _started(hass, control=True)
    try:
        await _wait_until(lambda: coordinator.settings_snapshot(SERIAL) is not None)
        numbers, _ = await _entities(coordinator)
        info = numbers["Battery Bulk Voltage"].device_info

        assert info["identifiers"] == {("dessmonitor", SERIAL)}
        assert info["manufacturer"] == "Local inverter"
    finally:
        await collector.stop()
        await coordinator.async_shutdown()
