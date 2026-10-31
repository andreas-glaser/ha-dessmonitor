# Later evidence, separate transports

- [transport_followup.json](transport_followup.json): direct DessMonitor Local
  observations. Five exact telemetry-only FC03 replies, packet/time references,
  false Eybond lengths, recovery delays and six distinct mixed-request pairs
  (including the non-failing pair). Also includes the short Local5s load window.
- [bridge_soak.json](bridge_soak.json): the later24.178h raw-RTU bridge run,
  with8522 complete cycles,119 errors and three recovered availability gaps.
  It is not a DessMonitor/Eybond stability test.

The five reply byte strings were checked against the original PCAP packet
payloads; Modbus CRC, IPv4 and TCP checksums were independently recomputed before
export. Only replies for known telemetry blocks are included. IP/TCP headers,
identity frames, product numbers, serials and account details are not attached.

In the transport file, source01 is the fault analysis, source02 the mixed-packet
analysis, source03 the recovery analysis, source04 the short load analysis and
source05/06 the two original captures. In the bridge file, source07 is the saved
status/event observation. Source hashes support the owner's audit against the
retained originals; they do not make omitted private material independently
available to reviewers. Counters/latencies are reported observations, not a
claim that the full private experiment is reproducible from these excerpts.

The source-number labels are local to this evidence bundle, not device IDs.
The raw PCAPs and bridge enrollment/configuration data remain private. Further
interpretation and limits: [review follow-up](../../research/PROTOCOL4_FOLLOWUP.md).
