# Local and Hybrid Telemetry

The integration can monitor inverter readings and change supported settings
through DessMonitor or ShineMonitor. Local telemetry adds a read-only path from
an Eybond-compatible Wi-Fi collector to Home Assistant. It does not require
inverter firmware changes. Settings changes continue to use the cloud API.

## Choose a mode

| Setup mode | Monitoring | Inverter configuration |
|---|---|---|
| Cloud API | Cloud readings | Supported settings through the cloud |
| Cloud API + preferred local telemetry | Local readings with cloud fallback | Supported settings through the cloud |
| Local network only (read-only) | Local readings without a cloud account | No configuration controls |

Cloud modes use your selected DessMonitor or ShineMonitor account. Hybrid mode
keeps the same config entry, entity IDs, and recorder history while fresh local
readings replace matching cloud readings. If one local route fails, only that
device falls back to cloud. If both transports fail briefly, the last cloud
snapshot remains available with Data Source `Cached Cloud`; cached readings do
not provide an offline way to change inverter settings.

One API entry can configure up to 16 local collectors. Standalone local mode
uses one collector per entry. All routes share one TCP listener safely and are
routed by their exact configured source address.

## Before setup

1. Give Home Assistant a fixed RFC1918 LAN address (`10.x`, `172.16-31.x`, or
   `192.168.x`). Do not use `0.0.0.0`.
2. Find the collector/logger IPv4 address in the router's DHCP client list and
   reserve it. This is not the inverter serial number.
3. Make sure the collector can initiate TCP connections to Home Assistant on
   port `8899`, and Home Assistant can send UDP to collector port `58899`.
4. If Wi-Fi client isolation or a VLAN is enabled, add only the required route
   and firewall rules. Do not expose either port to the internet.

The two connections travel in opposite directions:

| Purpose | Source | Destination | Protocol |
| --- | --- | --- | --- |
| Callback request | Home Assistant | Collector | UDP `58899` |
| Local telemetry session | Collector | Home Assistant | TCP `8899` |

TCP `8899` must be allowed through the Home Assistant host firewall as well as
any firewall between VLANs. No internet port forwarding is needed. Restrict
the rule to each reserved collector address. For example, a UFW host can use
one commented rule per collector:

```bash
sudo ufw allow in on <LAN_INTERFACE> proto tcp \
  from <COLLECTOR_IP> to <HOME_ASSISTANT_IP> port 8899 \
  comment 'DessMonitor local collector'
```

Replace all three placeholders before running the command. Repeat it for each
collector, then confirm the restricted rules with `sudo ufw status numbered`.

The setup sends a targeted `set>server=<HA IP>:8899;` callback request to the
configured private address. Firmware behavior differs, so this may briefly
interrupt a vendor-cloud session. The hybrid mode continues polling the API
and falls back automatically when local telemetry is unavailable.

## Recommended setup

For a new installation, select **Cloud API + preferred local telemetry**.
Choose the account platform and enter the normal API credentials first, then
paste the local collector addresses in the short second step. **DessMonitor
(default)** remains selected for existing accounts. Choose **ShineMonitor** for
that service. Cloud profile selection does not add a local driver: devcode 518
cloud telemetry is supported, but its local
protocol has not been verified. To use only the API, select
**Cloud API**. To skip the API and credentials entirely, select
**Local network only**.

For an existing cloud entry, do not create a new entry:

1. Open **Settings > Devices & services > DessMonitor > Configure**.
2. Select **Prefer local, fall back to cloud**.
3. Enter the fixed Home Assistant LAN IP. Paste all reserved collector IPs
   into the collector field, separated by commas, spaces, or new lines.
4. Leave the defaults unless a collector uses non-standard ports.
5. Confirm the callback request and submit.

The **Cloud API interval** and **Local polling interval** are independent.
Cloud keeps its existing 5-minute default for metadata, controls, cloud-only
fields, and fallback data. Local telemetry defaults to the recommended
5 seconds. A local update never triggers an extra API refresh.

In hybrid mode, settings still use the cloud. Their options and current values
can finish loading after local telemetry starts. The integration uses settings
already present in the normal cloud payload and retries missing control values
at most once per successful cloud refresh, without retrying on every local push.
Explicit value reads stop after three consecutive rounds recover nothing; a
round with partial recovery resets that budget. Ordinary cloud telemetry can
still fill values afterward. Reloading the integration starts a new budget.
`unknown` means no usable current value has been read; it is not an inverter
setting and is never written as a default. Previously known values are retained
through read failures. Select/number attributes show `control_transport: cloud`
and `value_status: not_loaded` or `last_known`. A known value or an enabled
control does not guarantee that the next cloud write will succeed.
Numeric controls reporting a non-numeric format (for example a time or date)
show `value_status: unsupported_format`; retrying the connection cannot turn
such a value into a numeric setting.

The `Data Source` sensor shows `Local`, `Cloud`, or `Cached Cloud`. Hybrid only
overlays a local device after matching it to canonical API or cached metadata;
it never invents a second entity identity. Disabling preferred-local mode
returns the same entities to API telemetry.

Each device carries its own `Data Source`. When the cloud answers for some
devices and times out for others, the ones that failed keep the readings of the
last cycle that reached them and report `Cached Cloud`, while their neighbours
report `Cloud`. In hybrid mode a healthy local route still makes such a device
`Local`. A device the API stops listing is removed instead of retained, so this
retention never keeps hardware alive that was taken off the account. Readings
labelled `Cached Cloud` can be arbitrarily old; the device's `Timestamp` sensor
shows when the cloud last answered for it.

If one inverter's status poll fails while another on the same collector succeeds,
only the responding inverter contributes to the new local snapshot. Hybrid uses
cloud data for the failed inverter until it responds again. Its device and sensor
identities are retained; a healthy neighbour cannot refresh its stale readings.

For a cloud-free installation, add another DessMonitor integration and choose
**Local network**. Use the advanced path only for a documented non-standard
port, product-number identity pin, or tunnel-code override.

The **Inverter address** setting is available during setup and in options. Its
value `0` preserves automatic discovery: identify address `1`, then check
contiguous addresses up to `16`, stopping at a missing or duplicate inverter.
Set `1` through `247` to target just that address, including addresses above
`16`. This selects where to read; it does not change the inverter's configured
address. Hybrid mode applies the setting to each listed collector. Existing
entries without the setting retain automatic discovery.

## Supported read-only drivers

- PI17/PI18 ASCII telemetry, with strict length and CRC validation. The inverter's
  `PI` response selects P17's escaped CRC encoding or PI18's raw CRC encoding;
  tunnel and cloud device codes do not select the field layout.
- PI30 ASCII telemetry with verified `QPI` identification and a valid standard
  17- or 21-field `QPIGS` status response. Reports grid/output voltage and
  frequency, output power/load, battery voltage/current/charge estimate,
  temperature, PV voltage and charging current. The 21-field layout also
  supplies PV charging power. Other layouts and protocol IDs fail closed;
  energy totals and local controls are not implemented for PI30.
- Standard SMG-family Modbus RTU telemetry, including cloud family devcode
  `2376`, with strict function-03, route, byte-count, and CRC validation.

- Modbus protocol-number `4` (register `184`), verified with read-only samples
  from an ANENJI ANJ-11KW-48V-W-P (cloud devcode `6544`). This layout uses
  separate output, battery, grid, dual-PV and energy blocks; it must not use
  the standard SMG `201..234` field positions. Detection selects the layout
  per inverter address and retains it for subsequent polling. Local controls
  are not provided. Sustained polling and reconnects still require hardware
  verification after installing this change.

PI18 uses its 28-field `GS` response for battery charging current and both PV
inputs, including PV2 voltage. It does not poll P17-only `GMN` or `GS2` commands.
Firmware metadata preserves all three CPU versions. Existing sensor identifiers
are retained; installing a decoder correction does not require deleting entities
or recorder history. Earlier incorrect readings are not rewritten.

Device detection is bounded and uses read queries only. Unsupported firmware
fails closed instead of guessing register layouts. Local write frame builders
and local control entities are intentionally absent.

An explicitly configured tunnel code `2452` tries the P17/PI18 driver first,
including when the collector reports `258` or `1`. Code `258` is shared by
different inverter families; it does not establish the inverter's protocol.
Automatic discovery and ambiguous hints retain the P17/SMG driver order.
PI30 is tried only after both existing drivers fail. Cloud devcodes are not
local protocol identifiers; leave the tunnel-code override at `0` unless a
working local route is known. Legacy SMG hints `1` and `2376` remain supported.

ASCII discovery tries the direct inverter route first, then a bounded collector
address `255` fallback in automatic mode. That fallback identifies at most one
inverter; `255` is never treated as its inverter address. Its inferred logical
address cannot be used to match a cloud device: hybrid mode requires the actual
inverter serial to match. Explicit inverter addresses disable the unaddressed
ASCII fallback. SMG's collector address `255` is different: its Modbus payload
still carries and validates the selected slave address.

PI30 and the additional ASCII routes have simulated-collector regression
coverage. The [SP-2200 report in issue #39](https://github.com/andreas-glaser/ha-dessmonitor/issues/39#issuecomment-5757878764)
confirms hardware discovery and polling through tunnel code `258` at address
`1`, with 16 local readings and a matching cloud inverter serial. Long-running
Home Assistant operation and recovery on that hardware still need testing.

## Contributor probe

The CLI can find callback-capable collectors on one `/24` or smaller private
network and create a sanitized read-only compatibility report:

```bash
python3 tools/cli/dessmonitor_cli.py local-scan \
  --listen-ip 192.168.1.10 --confirm-callback

python3 tools/cli/dessmonitor_cli.py local-probe \
  --listen-ip 192.168.1.10 \
  --collector-ip 192.168.1.50 \
  --confirm-callback \
  --output local-probe.json

python3 tools/cli/dessmonitor_cli.py analyze --redacted \
  --local-report local-probe.json \
  --output combined-analysis.json
```

For an inverter configured at address `5`, add `--device-address 5` to
`local-probe`. This targets only address `5`; `--max-address` continues to bound
automatic discovery and is ignored for an explicit address. Leave `--device-code`
at `0` unless a verified tunnel code is known.

Reports redact collector product numbers, IP addresses, and inverter serials
by default and are written with mode `0600`. Do not use
`--include-identifiers` for a report that will be shared publicly.
With `--output`, the probe also writes a report if the listener cannot start,
the collector callback times out, discovery fails, or polling fails. The command
still exits with an error. Share that file even when no inverter was found;
failed reports are for troubleshooting and cannot be merged with `analyze`.

Reports include `status`, the last `stage`, and bounded `diagnostics`: protocol,
command, device code, collector/inverter address, response byte count, elapsed
milliseconds, and outcome. A missing byte count means no payload was returned
to the query; zero means an empty payload was received. Header mismatches also
include the expected and received numeric routing fields. The `address_verified`
flag distinguishes a known address from an unaddressed ASCII route. Raw payloads
and exception text are not included in these diagnostic records. At most 128 query
records are retained, with additional attempts counted in `dropped_attempts`.
A random `probe_id` correlates a report and its log lines without identifying
the collector, including when several collectors are discovered concurrently.
An overall discovery deadline appears as a report-level `timeout`; the in-flight
query appears as `cancelled` because the deadline interrupts it.
An `unsupported_protocol` outcome means the inverter returned a protocol ID for
which this driver has no verified field layout.

The combined analysis matches a unique hashed collector product number and
inverter address, refuses ambiguous matches, and also writes mode `0600`.
For an unverified ASCII address, supply `--device-sn` explicitly; the combined
report only confirms identity when the actual serial matches.
Most collectors keep one callback connection. If Home Assistant already owns
it, briefly disable or stop that test instance while running `local-probe`,
then start it again; the configured integration reconnects automatically.

## Troubleshooting

- **No scan result:** use the router's DHCP list. Broadcast replies are often
  blocked by Wi-Fi client isolation, VLANs, or collector firmware.
- **Listener cannot start:** reserve TCP port `8899`, check that the configured
  Home Assistant address exists on the host, then use **Reconfigure** if the
  address changed.
- **Collector never connects:** verify the exact collector IP and both traffic
  directions above. Check the Home Assistant host firewall too. A warning is
  logged after two minutes without a callback.
- **Connected but no inverter is found:** create a sanitized local probe report
  and include the inverter model and collector firmware in a GitHub issue.
  The final error includes query outcome counts. Enable debug logging for
  `Local discovery` and `Local probe query` records showing each attempted route
  and failure classification. Also include `Local forward request` and
  `Local forward response` records: they show transaction IDs, routing fields,
  byte counts, and whether the reply matched an active request. Each TCP session
  has a random connection ID, so timestamps and transaction IDs can distinguish
  delayed replies from unrelated traffic across reconnects. `pending_transaction_id=0`
  means no request is active. These records contain no payload or device identifiers.
  `outcome=matched` confirms the transport header only; the driver still validates
  the payload's CRC and field layout.
  An unmatched reply remains rejected. A rejected reply is different from a timeout;
  changing the device code without this evidence may not help.
  A collector that reconnects is probed with the driver that last worked for
  it, and probing stops when that driver receives nothing at all, because
  silence says nothing about which protocol a collector speaks. A collector
  that answers is still probed in full, so new hardware is still identified.
- **Cloud data is selected:** inspect the Data Source sensor and Home Assistant
  logs. Local failures do not delete cloud-only fields or recorder history.
- **Telemetry keeps switching between local and cloud:** read the log lines
  around each switch. `Local inverter stopped answering status requests, while
  the collector itself still answers` means the collector is connected and the
  inverter behind it went quiet; polling is retried over the same connection
  for up to three minutes, and `Local inverter resumed answering` closes the
  window. `The local collector closed its connection` means the collector
  itself dropped the session and the integration is waiting for its next
  callback. The two have different causes: the first points at the link between
  collector and inverter, the second at the collector or the network. If the
  first one dominates, raising the local polling interval is worth trying.
  A collector answers a query the inverter ignores several seconds after the
  integration has stopped waiting for it, and its link to the inverter carries
  one transaction at a time: on a PI18 collector measured in #53, replies to
  unanswered queries arrived 8 to 11 seconds after the request against a 3
  second request timeout. The next query is now held back until that reply
  lands, so a single unanswered poll no longer takes the rounds behind it with
  it, but a longer interval still leaves the collector more room for its own
  cloud uploads.

Debug logging:

```yaml
logger:
  logs:
    custom_components.dessmonitor: debug
```

Debug messages avoid authentication tokens and full protocol payloads, but may
include collector product numbers, device serials, private IP addresses, and
live readings. Review logs and reports before sharing them.

## Testing discovery diagnostics from dev

If a maintainer asks you to test the development branch:

1. Download the [dev branch ZIP](https://github.com/andreas-glaser/ha-dessmonitor/archive/refs/heads/dev.zip).
2. Copy its `custom_components/dessmonitor/` directory over the same directory
   in your Home Assistant configuration, then restart Home Assistant.
3. Temporarily disable other local integrations or probes using this collector.
   Enable debug logging for DessMonitor and reload the integration once.
4. Capture the log sequence from collector connection through the first discovery
   failure, including `Local discovery`, `Local probe query`, `Local forward request`,
   and `Local forward response` lines. Include
   the configured device code, Data Source state, and the commit/version tested.
5. If using the contributor CLI, run the `local-probe` command above from the
   same downloaded checkout and attach `local-probe.json`, including on failure.
   Stop the HA local connection first so only the probe uses the collector.

Enabling debug logging does not alter timeouts or response validation. Report
the commit tested, since the development branch can also contain behavior fixes.
