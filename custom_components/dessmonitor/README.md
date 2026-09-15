# DessMonitor Home Assistant Integration

A custom integration for DessMonitor / SmartESS and SmartClient for Solar / ShineMonitor accounts in Home Assistant.
Cloud updates default to 5 minutes. Faster DessMonitor updates require its collection-acceleration service.

## Quick Setup
1. In Home Assistant: Settings > Devices & Services > Add Integration > "DessMonitor".
2. Choose the primary **DessMonitor cloud API**, the guided **API + preferred
   local telemetry** path, or read-only **Local network only**.
3. For either API path, choose **Account platform**. Keep **DessMonitor / SmartESS
   (default)** for existing accounts, or select **SmartClient for Solar / ShineMonitor**.
   Enter Username and Password; keep the Company Key default unless your installer supplied another.
4. Choose Update Interval:
   - 5 minutes: Standard rate (recommended)
   - 1 minute: Requires "Detailed Data Collection Acceleration" from DessMonitor

## Key Features
- Multiple inverter support with automatic discovery.
- Optional read-only local telemetry and preferred-local cloud fallback.
- Sensors for power, voltages, currents, frequency, temperature, load %, operating mode.
- Energy Dashboard compatible (use `*_total_pv_power`, `*_battery_power`, `*_grid_power`).
- Device configuration via select, number, and button entities (output priority, charger source, battery settings, buzzer mode, and more).
- Supported devcodes: 518, 2334, 2361, 2376, 2428, 2449, 2451, 2452, 2477, 2507, 6416, 6422, 6514, 6515, 6544.
- Diagnostic sensors available but disabled by default to avoid clutter.

## Device Configuration

The integration exposes inverter settings as Home Assistant entities, allowing you to read and change device configuration directly from your dashboard or automations.

For devcode 2477, the bulk, float, equalization, battery/utility return, and low
cut-off voltage dropdowns show only the API options for the reported 24 V or 48 V
rating. Detection uses `Rated Battery Voltage` or `Battery Piece`, never live
battery voltage. These six controls become unavailable if the rating is missing,
unsupported, or contradictory, or the API options cannot be validated. A log message
explains the reason; the controls recover automatically when valid data arrives.
Other controls retain their API options and ranges.

- **Select entities**: Settings with predefined options (output priority, charger source priority, battery type, buzzer mode, etc.)
- **Number entities**: Numeric settings with min/max ranges from the device (charging voltages, max currents, SOC protection values, EQ timers, etc.)
- **Button entities**: One-shot actions (clear record, reset user settings, forced EQ charging, exit fault mode)

All current values are read from the device at startup. Changes take effect immediately via the DessMonitor cloud API.

## Manage & Configure
- Change options anytime: Settings > Devices & Services > DessMonitor > Configure.
- Entities follow Home Assistant naming conventions under the `dessmonitor` domain.

## Requirements
- Home Assistant 2024.1.0 or newer.
- An account on one of the two supported platforms and internet access for cloud or hybrid mode.
- A fixed private Home Assistant LAN IP and collector IP for local telemetry.
- For local telemetry, outbound UDP `58899` from Home Assistant to the
  collector and inbound TCP `8899` from that collector to Home Assistant.
  Restrict firewall rules to reserved private collector addresses and do not
  expose either port to the internet.

## Troubleshooting
- Integration not found after install: Restart Home Assistant; ensure files are in `config/custom_components/dessmonitor/`.
- No devices or data: Confirm devices are online in the selected platform; check HA logs (Settings > System > Logs).
- Sensors not updating: Verify network access and account update interval; review logs for API errors.
- Configuration entities showing blank: Integration reads controls through the API and retries discovery after the next successful API refresh.
- Enable debug logging (configuration.yaml):
  ```yaml
  logger:
    logs:
      custom_components.dessmonitor: debug
  ```

## Notes
- Existing entries keep their profile, entity identities, and history without migration.
- Tokens renew using the expiry returned by the selected backend and are never reused across profiles.
- Devcode 518 cloud telemetry is supported; its local protocol and write controls have not been verified.
- Respect DessMonitor API limits; avoid excessively frequent polling.
- Control values are cached at startup and updated optimistically after writes. Restart HA to re-read values from the device.

## Support
- Issues: https://github.com/andreas-glaser/ha-dessmonitor/issues
