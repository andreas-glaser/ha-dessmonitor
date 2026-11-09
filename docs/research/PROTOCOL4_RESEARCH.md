# ANENJI protocol 4: document research and hardware evidence

## Scope and reproducible source

Verified hardware: **ANENJI ANJ-11KW-48V-W-P**, cloud devcode **6544**.
The existing cloud profile does not establish a local register layout. In the
v2.5.0 baseline, generic SMG detection decodes the legacy 201–234 map before
reading register 184 as optional metadata. This change adds the missing layout
and selects it before telemetry decoding.

Protocol source:

- Repository: https://github.com/PreK/esphome-anenji-11kw-native-modbus
- Commit: `55a330585846d57b4f24e6467201d8dde8985ee7`.
- File: [Communication.Protocol.No.3-10.docx](https://github.com/PreK/esphome-anenji-11kw-native-modbus/blob/55a330585846d57b4f24e6467201d8dde8985ee7/Communication.Protocol.No.3-10.docx).
- Document title: **Modbus_RTU Communication Description**.
- Stated version: **Version 1.0, November 2024**.
- SHA256 of the downloaded 58,006-byte DOCX:
  `c863516e3a842bea2c853151aa403b30f98354888a9dd80568cd092f0b3a9c70`.
- Re-read for this contribution on 2026-10-15 by extracting
  `word/document.xml` from the DOCX ZIP and inspecting the register table and
  introductory data-format sections.

Although the filename says No.3-10, the document's introductory list explicitly
names protocols 3, 4, 5 and 6. Only column 4 and the verified model are claimed
here. The file contains translation artifacts; source statements and observed
readings are therefore distinguished below. No vendor document, external source
code, ESPHome configuration or CRC implementation is redistributed in this PR.

## Addressing, framing and data types

The document specifies decimal register addresses, Modbus slave addresses 1–247,
FC03 reads and high-byte-first words. Multi-word values are high-word first.
Complete multi-register values must not be split by a query boundary.

`Int` is the document's signed integer type; `UInt` is unsigned. All analog
fields listed below are `Int`; mode and SOC are `UInt`. Daily energy is `UInt`,
total energy is `ULong` spanning 703–704. This supports two's-complement decoding
for the analog fields and separate unsigned decoding for SOC/energy.

Observed identifiers have separate roles:

| Identifier | Value | Evidence |
|---|---|---|
| Cloud devcode | 6544 | Official cloud analysis |
| Tunnel device code | 1 | Successful local probe |
| Collector tunnel address | 255 | Successful local probe |
| Modbus slave | 1 | Validated Modbus replies; address_verified=true |
| Protocol number, register 184 | 4 | Hardware discovery; document selector |
| Device model code, register 171 | 32771 | Hardware discovery and cloud metadata |

The implementation uses the existing tunnel/CRC validation and builds only
read requests. FC10 write examples in the document are not implemented.

## Implemented protocol-4 register facts

This is a concise factual mapping, not a reproduction of the document's table.
Scale means the divisor applied to the register value.

| Registers | Meaning | Type / divisor |
|---|---|---|
| 201 | Operating mode | UInt / 1 |
| 203 | Grid frequency | Int / 100 |
| 206 | AC charging power | Int / 1 |
| 207 | Power-flow extension flags; not a frequency | UInt; not published as frequency |
| 227 | Inverter frequency | Int / 100 |
| 231 | Inverter temperature | Int / 1 |
| 252, 253 | Total output current, output frequency | Int / 10, Int / 100 |
| 254, 255, 256 | Output active/apparent power, load percentage | Int / 1 |
| 277, 278, 279 | Battery voltage, current, power | Int / 10, Int / 10, Int / 1 |
| 280, 281 | SOC, DCDC temperature | UInt / 1, Int / 1 |
| 302, 303, 304, 305 | PV power, charger power, charging current, temperature | Int / 1, 1, 10, 1 |
| 338, 340 | Grid L1 voltage, active power | Int / 10, Int / 1 |
| 342, 343 | Inverter L1 voltage, current | Int / 10 |
| 346 | Output L1 voltage | Int / 10 |
| 351, 352, 353 | PV1 voltage, current, power | Int / 10, 10, 1 |
| 384 | Output L2 voltage | Int / 10 |
| 389, 390, 391 | PV2 voltage, current, power | Int / 10, 10, 1 |
| 702 | Energy today | UInt / 100 kWh |
| 703–704 | Energy total | ULong, `(high << 16) | low`, / 100 kWh |

Register 278 explicitly defines positive current as charging and negative as
discharging. Derived charging/discharging current entities split that signed
measurement without adding a device query.

Mode register 201 documents 0=Power on, 1=Standby, 2=Mains, 3=Off-grid,
4=Bypass, 5=Charging, 6=Fault. The candidate normalizes Mains and Bypass to
`Grid Mode`, consistent with the devcode 6544 cloud normalization of Bypass Mode.
That normalization does not mean hardware mode 4 was captured: fixture modes
are 2 and 3. Mode 4 is document-backed.

The baseline's register 215 battery-voltage interpretation is not defined by
this layout. Registers 606/607 are output voltage/frequency **settings**, not
live output measurements. Neither is substituted for telemetry.

Polling blocks (start, count): `(201,7)`, `(227,5)`, `(252,5)`, `(277,5)`,
`(302,4)`, `(338,16)`, `(384,8)`, `(702,3)`. The snapshot must contain every
requested word; any failed/corrupt block fails the cycle instead of publishing
partially fresh telemetry. The selected layout is retained independently per slave.

## Hardware evidence included with this PR

Directory `docs/evidence/protocol4/`:

- `analysis_6544.json`: official redacted cloud analysis, exported
  **2026-10-13 22:35:18**; measurement Timestamp **22:29:07**.
- `local_probe_6544.json`: official read-only probe, received **2026-10-15**;
  the report contains no exact measurement timestamp. Status success, stage
  complete, **35 readings, 19 successful requests, no failed requests**.
- `combined_analysis_6544.json`: built offline with the CLI's evidence helpers;
  official checksum verification succeeds. It matches by collector hash and
  verified slave address, not by assuming equal cloud/local serials.
- `tests/fixtures/protocol4_hardware.json`: two register snapshots from
  2026-10-13 and a daytime PV-producing snapshot from 2026-10-15.

The cloud/local exports are **not simultaneous**. The combined report preserves
the original cloud export date. Identity fields are redacted or represented by
the CLI's standard correlation hashes. No account credentials or private captures
are included.

Local-probe example: battery 53.9 V / 60.9 A / 3282 W, AC charging 3375 W,
grid 4801 W, output 1224 W, frequencies near 50 Hz, energy 10.85/341.04 kWh.
Daytime fixture: battery current 21.7 A, PV power 2303 W, PV1/PV2 power
1127/1177 W, total energy 337.23 kWh. Different registers may update at slightly
different times; these figures are not offered as an exact simultaneous power balance.

SHA256 of the attached exports:

| File | SHA256 |
|---|---|
| analysis_6544.json | `3b8507b5d3dcbc13e4cca20a996cb2977c7ac08b6f38034f1b9ac1a02962e191` |
| local_probe_6544.json | `23488a2096b04d6bded99ddb1e77a4f51f5af3addf8d7a5c54fe9df7e7656995` |
| combined_analysis_6544.json | `f57ad4d9b083f80bc7363cbf2a619529d08b45e471c6e71e3a9d914ac1c8b5c3` |

Recheck analysis integrity offline:

```bash
python tools/cli/dessmonitor_cli.py verify docs/evidence/protocol4/analysis_6544.json
python tools/cli/dessmonitor_cli.py verify docs/evidence/protocol4/combined_analysis_6544.json
```

## Verification boundaries

- Physical testing is limited to ANJ-11KW-48V-W-P. Legacy SMG and ASCII drivers
  have automated regression coverage; no additional physical models are claimed.
- Fixtures prove low-word energy values and crossing the signed-16-bit boundary.
  Their high words are zero. High-word ordering is established by the document,
  not independently by those captures.
- A failed read of 184 can still use the compatibility fallback for legacy
  firmware lacking that register. The known bad protocol-4 legacy capture is
  rejected by voltage plausibility; a different false positive during a failed
  selector read remains a residual risk to discuss, not a proven hardware failure.
- At the original PR submission, later captures had not reproduced the earlier
  malformed-frame errors. Subsequent October 16 captures did establish a missing
  Eybond-envelope failure; see the [review follow-up](PROTOCOL4_FOLLOWUP.md).
  This decoder PR does not repair that transport failure.
- Successful Local publication on HA is confirmed, but neither continuous
  availability of cloud-only functions nor the cause of earlier dashboard
  symptoms is established by this protocol work.

## October 24 review follow-up

[User-visible discovery/merge changes and longer-run evidence](PROTOCOL4_FOLLOWUP.md)
separate the direct Eybond observations from later AT/raw RTU bridge observations.
The new observations do not expand the hardware support claim to other models.
