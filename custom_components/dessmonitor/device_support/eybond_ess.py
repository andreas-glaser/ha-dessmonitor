"""The setpoint vocabulary Eybond's own ESS collectors return as readings.

Devcodes 6514, 6515 and 6544 are three Eybond collectors that render the
inverter's configuration into the telemetry call beside the live measurements.
Each setpoint arrives spelled exactly as a control field of the same device and
carrying the value that control reads back, down to the vendor's own
``bat_eq_time`` and the two spaces in "SOC Protection value of OP1  In off-grid
mode". Their control ids are Eybond's (``bat_eybond_read_``, ``bse_eybond_read_``,
``sys_eybond_read_``), which is what marks the family: the Voltronic PI30
collectors in ``eybond_voltronic`` use a different vocabulary and a different
id scheme.

Three devcodes with one vocabulary is the reason this file exists. The support
report counts a reading that reaches no entity, and a setpoint is not a reading
being dropped, so each of the three told its owner that readings were missing
when none were: twenty on 6514 (#69), twenty on 6544 across three inverters
(#77), seventeen on 6515 (#76). Of the 46 titles below, 30 appear in all three
downloads and every one appears in at least one, so copying the list per
devcode would be three lists to keep in step where the evidence says there is
one.

A profile opts in by importing this table, which keeps adding a devcode to the
family a decision backed by its own download. Nothing here is a guess:
``tests/test_eybond_ess_settings.py`` reads the committed downloads and fails
on a title that no device reports as both a reading and a control.

Two kinds of title are deliberately absent. "Equipment type" and "Protocol
Number" describe the hardware rather than configure it, carry no unit and are
not controls. "Output Voltage Setting" resolves to a sensor of its own that
installations publish today and must keep; declaring a reading a setting never
removes an entity, because a title that resolves is never consulted here, but
the list stays honest about what it claims.
"""

from __future__ import annotations

# Each entry is a title at least one committed download reports as a reading
# and names as a control field of the same device. The devcodes in the comments
# are the ones whose evidence carries that title.
SETTING_READINGS: set[str] = {
    # Battery charging and protection setpoints, published as number entities.
    "Battery overvoltage protection point",
    "Maximum charging voltage",
    "Floating charge voltage",
    "Mains mode battery discharge recovery point",
    "Mains mode battery low voltage protection point",
    "Off-grid mode battery low voltage protection point",
    "Constant pressure to float waiting time",
    "Maximum charging current",
    "Maximum mains charging current",
    "Maximum discharge current protection",
    "Low DC Protection SOC In AC Mode",
    "Low DC Recovery SOC In AC Mode",
    "Battery Low Cut Off SOC",
    # Equalization setpoints. "bat_eq_time" is the vendor's own title.
    "Eq charging voltage",
    "bat_eq_time",
    "Eq timeout exit",
    "Eq charging interval",
    "Battery Eq mode enable",
    # Mode and behaviour settings, published as select entities.
    "Battery Type",
    "Buzzer Mode",
    "LCD backlight",
    "LCD automatically returns to the homepage",
    "Input Mode",
    "Output mode",
    "Output Frequency Setting",
    "Overload automatic restart",
    "Automatic restart when over temperature",
    "Overload transfer to bypass enable",
    "Automatic mains output enable",
    "Boot method",
    "Remote switch",
    # 6514 only so far: the lithium activation switch its collector offers.
    "Automatic activation for lithium battery",
    # The second output stage, on the split-phase collectors (6514, 6544).
    "Off-grid mode OP1 battery low voltage protection point",
    # The vendor pads this title with two spaces; titles compare collapsed.
    "SOC Protection value of OP1  In off-grid mode",
    "OP2 overload alarm setting",
    "Whether the OP2 allows the output",
    # The scheduled secondary priorities and their windows (6515, 6544). The
    # start and end times read as HH:MM and are the values of the temporal
    # controls each profile declares.
    "Secondary Output Priority",
    "Secondary Output Priority Start Time",
    "Secondary Output Priority End Time",
    "Secondary Charging Priority",
    "Secondary Charging Priority Start Time",
    "Secondary Charging Priority End Time",
    # The inverter's clock, which each collector names its own way: 6544 sends
    # "Inverter Date" and 6515 " Inverter Time", leading space included.
    "Inverter Date",
    "Inverter Time",
    # Behaviour switches seen on 6515 and 6544.
    "Dry contact",
    "Energy-saving mode switch",
}
