# Local and Hybrid Telemetry

Local telemetry is a read-only path from an EyeBond-compatible Wi-Fi
collector to Home Assistant. It does not require inverter firmware changes and
does not expose local write controls.

## Choose a mode

- **DessMonitor cloud API** is the primary and existing default. It keeps all
  cloud sensors and controls unchanged.
- **DessMonitor API + preferred local telemetry** starts with the API for
  canonical device identity, metadata, controls, and fallback. It keeps the
  same config entry, entity IDs, and recorder history while fresh local
  readings replace matching cloud readings. If one local route fails, only
  that device falls back to cloud. If both transports fail briefly, the last
  cloud snapshot remains available with Data Source `Cached Cloud`.
- **Local network** creates a standalone, read-only entry without DessMonitor
  credentials or internet access.

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

The setup sends a targeted `set>server=<HA IP>:8899;` callback request to the
configured private address. Firmware behavior differs, so this may briefly
interrupt a vendor-cloud session. The hybrid mode continues polling the API
and falls back automatically when local telemetry is unavailable.

## Recommended setup

For a new installation, select **DessMonitor API + preferred local telemetry**.
Enter the normal API credentials first, then paste the local collector
addresses in the short second step. To use only the API, select
**DessMonitor cloud API**. To skip the API and credentials entirely, select
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

The `Data Source` sensor shows `Local`, `Cloud`, or `Cached Cloud`. Hybrid only
overlays a local device after matching it to canonical API or cached metadata;
it never invents a second entity identity. Disabling preferred-local mode
returns the same entities to API telemetry.

For a cloud-free installation, add another DessMonitor integration and choose
**Local network**. Use the advanced path only for a documented non-standard
port, product-number identity pin, or device-code hint.

## Supported read-only drivers

- PI17/PI18 ASCII telemetry, with strict length, escaping, and CRC validation.
- Standard SMG-family Modbus RTU telemetry, including cloud family devcode
  `2376`, with strict function-03, route, byte-count, and CRC validation.

Device detection is bounded and uses read queries only. Unsupported firmware
fails closed instead of guessing register layouts. Local write frame builders
and local control entities are intentionally absent.

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

python3 tools/cli/dessmonitor_cli.py analyze \
  --local-report local-probe.json \
  --output combined-analysis.json
```

Reports redact collector product numbers, IP addresses, and inverter serials
by default and are written with mode `0600`. Do not use
`--include-identifiers` for a report that will be shared publicly.
The combined analysis matches a unique hashed collector product number and
inverter address, refuses ambiguous matches, and also writes mode `0600`.
Most collectors keep one callback connection. If Home Assistant already owns
it, briefly disable or stop that test instance while running `local-probe`,
then start it again; the configured integration reconnects automatically.

## Troubleshooting

- **No scan result:** use the router's DHCP list. Broadcast replies are often
  blocked by Wi-Fi client isolation, VLANs, or collector firmware.
- **Listener cannot start:** reserve TCP port `8899`, check that the configured
  Home Assistant address exists on the host, then use **Reconfigure** if the
  address changed.
- **Collector never connects:** verify the exact collector IP, UDP port
  `58899`, TCP port `8899`, and inter-VLAN firewall direction.
- **Connected but no inverter is found:** create a sanitized local probe report
  and include the inverter model and collector firmware in a GitHub issue.
- **Cloud data is selected:** inspect the Data Source sensor and Home Assistant
  logs. Local failures do not delete cloud-only fields or recorder history.

Debug logging:

```yaml
logger:
  logs:
    custom_components.dessmonitor: debug
```

Debug messages avoid authentication tokens and full protocol payloads. Still
review logs and reports before sharing them.
