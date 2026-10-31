# Protocol-4 review follow-up — 2026-10-24

This is a de-identified summary of later observations on the same
ANENJI ANJ-11KW-48V-W-P, protocol 4 / model 32771 / slave 1.
The original [document and fixture evidence](PROTOCOL4_RESEARCH.md) remains valid.
Raw private captures are not attached, and these observations are not a new
installation or soak test of the exact focused PR commit.

Compact [machine-readable excerpts and provenance](../evidence/protocol4/FOLLOWUP.md)
now accompany this summary, including the exact five telemetry reply byte strings.

## User-visible behavior beyond the new decoder

- A successful read of register 184 selects the layout before decoding. A value
  other than 0, 1 or 4 is rejected instead of interpreted with the legacy map.
  A failed selector read still follows the legacy compatibility fallback.
  Automatic multi-slave discovery stops after a failed/unsupported slave once
  an earlier device was accepted; this can hide later addresses in that scan.
- Legacy snapshots now require at least one strictly positive voltage among
  Output, Battery, PV and Grid. Present but zero-valued fields are insufficient.
  This protects against the captured false-positive legacy decode but changes
  validation for all legacy SMG users, not just protocol 4.
- During a matched hybrid overlay, Main and Current cloud fields with a shared
  mapped title remain distinct when there is no local replacement. The sensor's
  first-match lookup can therefore show a different value from the old merge,
  which retained the last duplicate. Entity IDs do not change, but consumers of
  that sensor may observe a changed value. Cloud-only and unmatched devices do
  not use this overlay and retain their existing behavior.

These changes are called out in the changelog for release planning. They are
not evidence that other register maps work with either the old or new decoder.

## Non-4 evidence

The primary November 2024 document explicitly describes protocols 3, 4, 5 and 6;
its filename alone does not establish all numbers through 10. Our hardware has
only established protocol 4.

A separate public source records a captured protocol-3/model-29440 fingerprint
for ANENJI HHS 11kW without parallel:
[Eybond Local model catalogue at dcad8ac](https://github.com/groove-max/ha-eybond-local/blob/dcad8ac934b7741a161d5aaf3b8658678446dc9d/catalog/inverter_models/models/anenji_hhs_11kw_wifi_no_parallel.json).
It reports partial telemetry validation and no hardware-validated local writes
for that model. This is an external example of non-4 hardware, not a prevalence
estimate, a claim of our own testing, or proof the old DessMonitor legacy map
decoded that unit correctly. No additional layout is enabled by this PR.

## Direct DessMonitor / Eybond observations

On October 15, a roughly 6m46s Local-5s window contained 655 matched replies,
about 96 requests/minute, median RTT 191ms, p95 557ms and maximum 1927ms.
The eight-read cycle is about six times the legacy average of one live read
per cycle plus two status reads every sixth cycle, excluding retries/discovery.
That short window does not establish an indefinitely safe polling frequency.

Two October 16 captures cover 12:08:57–13:23:09 and 13:23:34–16:29:10 UTC+3,
about 4h20m in total. They contain five incoming FC03 replies with valid Modbus
CRC and byte count but no expected eight-byte Eybond envelope. Interpreting
their register data as the missing transport header reproduces the exact
invalid-length warnings. The same captures have no relevant TCP sequence gaps
or conflicting retransmitted bytes at those transitions.

All five failures follow overlapping forwarding and heartbeat traffic. One
other mixed-request pair did not fail, so coalescing alone is not proven a
sufficient trigger. The immediate framing failure is established; firmware
internals and a general polling-frequency threshold are not. Reconnection and
complete polling resumed after the failures. Local heartbeat/forward
serialization was subsequently developed separately; it is not included here
and a short successful post-install observation is not long-term qualification.

The longer capture span must not be presented as a single unchanged-version,
fixed-interval, error-free 5s acceptance run.

## Longer run through a different collector transport

A separate InverterLocalBridge implementation later used the same hardware and
the same eight telemetry blocks:
`201/7, 227/5, 252/5, 277/5, 302/4, 338/16, 384/8, 702/3`.
Native identity reads again returned protocol 4 and model 32771.

However, it uses an intercepted outgoing collector connection on port 18899:
AT identification followed by **raw Modbus RTU over TCP**, rather than the
direct Local Eybond envelope/heartbeat path. It is not Modbus TCP with an MBAP
header. Only one telemetry polling owner is active; the second collector
channel is passive after admission. Additional settings/clock reads share the
implementation's transaction scheduling.

The saved October 22–23 run of app 0.16.0 records:

| Metric | Observation |
|---|---:|
| Runtime, one boot | 24.178 hours |
| Poll interval | 10 seconds |
| Complete telemetry cycles | 8,522 |
| Recorded polling errors | 119 |
| Error classes | 89 TimeoutError, 29 ControlError, 1 ConnectionError |
| Maximum gap between complete snapshots | 44.080 seconds |
| Recovered availability gaps after initial enrollment | 3 |

The counters and 119 current-boot error events were checked against the saved
JSON. ControlError is a wrapper and does not by itself indicate a setting write
or establish the underlying transport error. The internal journal was healthy.
The earlier October 20 run had incomplete journal retention and is not used as
evidence of a fully archived 24-hour run.

This later run strengthens evidence for sustained use of the register layout,
but does **not** establish fault-free DessMonitor Local-5s behavior, vendor-cloud
coexistence or a common physical cause for the two transports' failures. No
change to the polling interval or transport is made by these review notes.
