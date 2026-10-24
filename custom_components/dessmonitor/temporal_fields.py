"""Verified cloud temporal field classification, independent of HA platforms."""

from __future__ import annotations

from typing import Any

# Cloud control IDs, not local Modbus write addresses.
_FIELDS = {
    "bat_eybond_read_43988": "time",
    "bat_eybond_read_43989": "time",
    "bse_eybond_read_43979": "time",
    "bse_eybond_read_43980": "time",
    "sys_eybond_read_44023": "text",
}


def temporal_control_kind(devcode: Any, field_id: Any) -> str | None:
    """Select only the field IDs verified for this cloud device family."""
    if str(devcode) != "6544" or not isinstance(field_id, str):
        return None
    return _FIELDS.get(field_id)
