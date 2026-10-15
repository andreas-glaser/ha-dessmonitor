# Duplicate collector polling: evidence and reproduction

Baseline: v2.5.0, `5b90b75057c0bef8e677918413a0f63104a0ea48`.

Request analysis found one physical collector returned through two projects.
`_fetch_collectors` passed both rows to discovery/telemetry even though the
downstream API queries are keyed by PN rather than project ID. The later
dictionary merge hides the duplicate result but not the duplicate requests.

For that account layout, deduplicating PN removes two ordinary-cycle requests:
**9 to 7**. These counts exclude startup control discovery and are not universal.

Synthetic reproduction in `tests/test_coordinator_startup.py` returns
`[{"pn":"SHARED","pid":1},{"pn":"SHARED","pid":2}]`, then checks that discovery
and telemetry are each called once. Another test retains distinct PNs.
The final collector metadata comes from the last occurrence, preserving the
effective result of the original per-project merge.

This small fix is independent of protocol-4 decoding and control-value recovery.
It does not change the poll interval or explain external API timeouts.
