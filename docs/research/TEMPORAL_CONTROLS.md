# Schedule and inverter-clock controls: client research and migration

This contribution depends on cloud control-value recovery. It remains a draft
pending that prerequisite and physical write/readback verification.

| API field (devcode 6544) | Observed read | Proposed entity |
|---|---|---|
| bat_eybond_read_43988 | 15:00 | time |
| bat_eybond_read_43989 | 20:00 | time |
| bse_eybond_read_43979 | 15:30 | time |
| bse_eybond_read_43980 | 17:00 | time |
| sys_eybond_read_44023 | 2026-10-13 13:36:16 | validated text |

Values were observed in device logs. The official redacted analysis records
these field IDs as generic value controls with no unit or hint. The number
platform therefore created numeric entities for non-numeric values.

## Serialization evidence

Public client inspected on 2026-10-15:
https://www.dessmonitor.com/js/chunk-4eb723b8.221dae61.js

For generic fields the read handler copies `queryDeviceCtrlValue.dat.val` into
`controlvalue`; `xiafaInverter` passes it literally as `ctrlDevice.val`. These
five IDs have no dedicated conversion. This supports string round-tripping,
but does not establish successful writes or every device-supported value.
No vendor JavaScript is copied into the implementation.

The client's datetime widgets for `system_time`/`sys_system_time` and compact
time-of-use API for other devcodes are different paths, not evidence for these IDs.

## Representation and tests

Schedule fields accept HH:MM with zero seconds and no timezone conversion.
The inverter clock is validated YYYY-MM-DD HH:MM:SS text: its timezone is unknown,
whereas HA DateTimeEntity requires an aware timestamp. No automatic clock sync
or assumption that the device uses HA's zone is introduced.

Tests cover calendar validity/leap dates, midnight, rejection of non-zero seconds,
timezone annotations, `24:00` (including Python 3.14 normalization), exact request
values, failed writes, read recovery, repeated samples and real HA state publication.
The new platforms share cloud control caching and are absent in local-only mode.

## Migration and rollback

Only the five advertised IDs on devcode 6544 are reclassified. Corresponding
old number registry entries are disabled, not deleted; user-disabled entries
and unrelated entities are preserved. New IDs use serial + API field ID.
Update dashboards/automations to time/text IDs and services for these five fields.
Uninstalling this code does not automatically re-enable old numbers; rollback
requires explicit registry re-enablement. No installed package has yet been
updated to exercise this migration on the user's device.

Physical write/readback is still required. API success alone is not device
confirmation. Existing read-only telemetry work is independent of this candidate.
