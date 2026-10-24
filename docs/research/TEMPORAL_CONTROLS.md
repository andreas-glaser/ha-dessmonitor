# Schedule and inverter-clock controls: client research and migration

This contribution depends on cloud control-value recovery, including its bounded
retry follow-up. It remains a draft: cloud write/readback evidence is partial,
as detailed below, and does not cover all five paths on this exact PR build.

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
old number registry entries are disabled, not deleted. Their identity suffix is
computed by the same exported helper as `number.py`, without trimming names or
changing existing IDs (including the leading-space Inverter Date case).
Field classification lives separately so importing that helper cannot create a
number/temporal platform import cycle. New IDs use serial + API field ID.

Each old entry's registry options under `dessmonitor` record
`temporal_number_migrated: true` through the supported entity-registry API.
The migration records user-disabled and already integration-disabled entries
too, without changing their disabled flag. Subsequent user re-enables survive
fresh discovery, reload and persisted-registry reload. Unrelated options and
entries belonging to another config entry are preserved. Missing old entries
are not marked; a later discovered legacy entry can still be migrated.

This requires a **minor release with a prominent migration note**, rather than
an unannounced patch. Update dashboards/automations to time/text IDs, and use
`time.set_value` / `text.set_value` rather than `number.set_value` for these fields.
Re-enabling an obsolete number does not create a live numeric implementation in
the new platform; the registry/history record and user's choice are retained.
Uninstalling this code does not automatically re-enable old numbers. Rollback
requires explicit registry re-enablement and restoration of old UI references.
The marker remains on the old registry record if the temporal version is later
reinstalled; it is not an instruction to override the user's disabled flag.

An earlier combined build exercised the original migration on October 16:
97 prior registry entries/IDs retained, five numbers disabled and five new
time/text entries added, giving 102 entries. The revised one-time migration
is tested offline with HA's real registry; it has not been installed on hardware.

## Later write/readback observations, separate by transport

The [compact cloud evidence](../evidence/temporal_controls/README.md) includes
selected command/readback records, failures, reconciliation and source hashes.

| Setting | Vendor HTTP API / DessMonitor | Separate native bridge |
|---|---|---|
| Secondary charging start/end (43988/43989) | October 17: 15:00/20:00 changed to 20:01/20:02; separate `queryDeviceCtrlValue` calls returned the changed strings; baseline restored | FC16/FC03 configuration tests on registers 634/635 |
| Secondary output start/end (43979/43980) | Successful cloud writes not established | October 19: register603 15:30→15:31→15:30 and604 17:00→17:01→17:00, with ACK and independent readback |
| Inverter Date (44023) | Read format established; successful cloud write not established | October 22: one FC16 write to696–701 and independent readback; clock drift reduced from52.624s to about2s |

The vendor-API observations used a later combined build with separate readback,
not an isolated installation of this exact PR head. They included failures:
the first end-time write timed out and a later independent read still showed
20:00. A subsequent deliberate attempt followed that reconciliation and read
back20:02. The start-time write returned successfully, but its first external
read timed out; a later separate read returned20:01. All test settings were
restored. These are configuration observations, not a physical demonstration
of the scheduled behavior or a claim of error-free API operation.

The bridge verifies the same protocol4/model32771 inverter, but uses intercepted
collector TCP with AT identification and raw RTU. Native schedules are HHMM
integer words, and the calendar is six year/month/day/hour/minute/second words.
Native success does not validate `ctrlDevice` string serialization, cloud field
IDs or a vendor timezone contract. The cloud IDs are not Modbus addresses.
No automatic clock synchronization or local writes are added by this PR.

Existing read-only telemetry work is independent of this candidate. API success
alone is not device confirmation, and remaining cloud paths keep this a draft.
