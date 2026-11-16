"""Helpers shared by tests that exercise the control write seam."""

from __future__ import annotations

from typing import Any


def bind_cloud_control_writes(coordinator: Any) -> Any:
    """Give a mock coordinator the real cloud write seam, bound to the mock.

    Every control entity writes through ``async_set_control_value`` so that
    one place decides which transport carries a write: the cloud, the local
    link, or local-then-cloud. A mock coordinator in a test is standing in for
    a cloud one, so it gets the real cloud implementation rather than a mock
    of it. The tests then still assert what they always asserted - the exact
    ``set_device_control_value`` call the platform receives - which is what
    makes them evidence that moving the seam did not change the cloud path.
    """
    from types import MethodType

    from custom_components.dessmonitor import DessMonitorDataUpdateCoordinator

    for name in ("async_set_control_value", "record_control_write"):
        setattr(
            coordinator,
            name,
            MethodType(getattr(DessMonitorDataUpdateCoordinator, name), coordinator),
        )
    return coordinator
