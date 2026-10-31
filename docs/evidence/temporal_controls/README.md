# Partial cloud schedule write/readback evidence

**October31 update:** [one schedule field was confirmed on the inverter display
and by delayed independent cloud read](HARDWARE_20261031.md), with explicit
restoration evidence. Calendar writes remain unverified. The October17 record
below is retained separately and must not be presented as the newer experiment.

[cloud_schedule_readback.json](cloud_schedule_readback.json) contains allowlisted
October17 observations from the later combined DessMonitor build. It excludes
account/device identifiers, URLs, authentication, HA entity IDs and peer addresses.

| Operation | Command result | Separate observation |
|---|---|---|
| End20:00→20:02, first attempt | Service failure after30.098s | End remained20:00 |
| Start15:00→20:01 | Service acknowledged in1.863s | First read failed; later read20:01 |
| End20:00→20:02, after reconciliation | Service acknowledged in1.916s | Read20:02 |
| Restore start20:01→15:00, first attempt | Transport failure | First read unusable; later reconciliation20:01 |
| Restore end20:02→20:00 | API error2 | Separate read20:00 |
| Restore start20:01→15:00 after Local pause | API acknowledged | Separate read15:00 |

The selected reads preserve the baseline, failed initial reads, reconciliation,
later observations and restoration. Each of the first three recorded service
operations issued one service call. The restoration path used a narrow vendor
API helper. No new commands were issued while preparing this evidence.

These are requested values and observed outcomes, not raw HTTP payload capture
or inspection of the inverter display. Do not compute cross-source request
latencies by subtracting tool and HA timestamps: those clocks differed. The
recorded service duration and operation labels have distinct roles.

Source08 is the retained measurement summary; source09–11 the three service
operation results; source12/13,14/15,16/17 are restoration intent/result pairs.
Hashes allow the owner to reconcile excerpts with retained originals. Full
private records are not attached and hashes alone do not independently prove
the physical experiment. The failure on restoration followed by an observed
original value must not be simplified to either "API error means unchanged"
or "API acknowledgement proves device success".

Only two cloud fields are covered:43988/43989. Output schedules43979/43980 and
clock44023 still lack cloud-write confirmation. Native Modbus results do not
close that gap. See [research and migration](../../research/TEMPORAL_CONTROLS.md).
