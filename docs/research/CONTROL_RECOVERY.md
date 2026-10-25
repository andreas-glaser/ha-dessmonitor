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

## Review follow-up: bounded missing-value reads

The original once-per-revision rule did not limit the lifetime cost of a field
that never resolves. The maintainer's fix, commit
`7337136b9354c7cc47e44c4ed99050c351a1ff3f`, stops explicit value reads after three
consecutive rounds without recovery, including the initial round. Any round
that fills a missing field resets the per-device budget. One info log explains
the stop; reloading the integration creates a new budget. This limits value
reads, not definition discovery or all API traffic.

Ordinary cloud telemetry still seeds values after the budget is exhausted.
Regression coverage checks both that permanently unreadable fields stop costing
requests and that already-created select/number entities recover from a later
ordinary cloud refresh without another per-field read. Failed reads do not
trigger control writes. The dependent time/text platforms use the same budget.

Updated against upstream dev `9ddc66310005c58221e272b8f339ba4bdc6e4347`.
Numeric writes retain upstream's integral formatting (`30`, not `30.0`) while
cache synchronization retains this PR's protection of unchanged raw values.
