# Cloud control recovery: evidence and review notes

Baseline: v2.5.0, `5b90b75057c0bef8e677918413a0f63104a0ea48`.
Observed on ANENJI ANJ-11KW-48V-W-P / devcode 6544: current select/number
settings can remain unknown following failed initial control-value reads.

The baseline treats a cached partial/empty result as completed discovery.
Existing select entities also do not consume late recovered values. The fix
seeds settings from ordinary cloud telemetry, retries only missing values once
per successful cloud revision and notifies existing entities after recovery.
Local pushes do not increment that revision or trigger additional field reads.

`tests/test_control_recovery.py` provides reproducible synthetic API cases for:
initial partial reads, definition recovery, external changes, in-flight reads,
accepted writes, placeholder filtering, cloud outages and repeated timestamps.
Shared locking prevents duplicate per-device read batches across platforms.

The same cloud sample identity and local pushes do not replay a pre-write value.
A new timestamp may update the displayed setting even if that field is still
stale. There is no read-after-write acknowledgement barrier. Cloud acceptance
of a write does not prove the physical inverter applied it.

The source of settings is the original cloud snapshot, not the locally merged
telemetry. Preservation of distinct main/current fields in the hybrid merge is
included in the separate protocol-4 contribution; it is not silently duplicated
here. The recovery tests and code in this branch work on the upstream baseline.

Intermittent API TCP failures were observed outside the integration. This PR
does not claim to repair the server/network or retry control writes. Schedule
and clock entity typing is a separate, dependent contribution.

No raw account logs or identifiers are needed to reproduce these tests.
