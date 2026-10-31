# DessMonitor / ShineMonitor for Home Assistant

Monitor your solar inverter and configure supported settings directly in Home Assistant through DessMonitor or ShineMonitor. Track solar production, battery status, and energy use with the same account you use in SmartESS, SmartClient for Solar, or a compatible rebranded app. Configuration uses the cloud; optional local monitoring is read-only and requires compatible hardware.

For Android and iOS downloads, see the [platforms and mobile apps table](../../README.md#platforms-and-mobile-apps).

## Quick Setup
1. In Home Assistant: Settings > Devices & Services > Add Integration > "DessMonitor".
2. Choose **Cloud API**, **Cloud API + preferred local telemetry**, or
   **Local network only (read-only)**.
3. For either API path, choose **Account platform**. Keep **DessMonitor (default)**
   for existing accounts, or select **ShineMonitor**.
   Enter Username and Password; keep the Company Key default unless your installer supplied another.
4. Choose Update Interval:
   - 5 minutes: Standard rate (recommended)
   - 1 minute: Requires "Detailed Data Collection Acceleration" from DessMonitor

## Key Features
- Supported inverter configuration from dashboards and automations via select, number, and button entities (output priority, charger source, battery settings, buzzer mode, and more).
- Multiple inverter support with automatic discovery.
- Optional read-only local telemetry and preferred-local cloud fallback.
- Sensors for power, voltages, currents, frequency, temperature, load %, operating mode.
- Energy Dashboard support where suitable energy sensors are available; see the [energy and power sensor guidance](../../README.md#energy-dashboard).
- Supported devcodes: 518, 632, 2334, 2361, 2376, 2428, 2449, 2451, 2452, 2477, 2507, 4743, 6416, 6422, 6514, 6515, 6544.
- Diagnostic sensors available but disabled by default to avoid clutter.

## Device Configuration

In cloud and hybrid modes, the integration exposes supported inverter settings as Home Assistant entities. Open your inverter's device page under **Settings > Devices & Services > DessMonitor**, or add its controls to dashboards and automations. Control discovery runs in the background, so settings can appear after sensor readings.

Settings changes use the selected platform's cloud API even when monitoring uses a local connection. Local-only mode provides monitoring without configuration controls.

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

Current values and available settings are fetched from the selected cloud platform. Changes are sent through that platform's API; available controls depend on the device.

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
- Respect your platform's API limits; avoid excessively frequent polling.
- Select and number entities update their displayed values after successful API writes. Numeric settings included in regular telemetry also refresh when new readings arrive; changes made outside Home Assistant may not appear automatically for other controls.

## Support
- Issues: https://github.com/andreas-glaser/ha-dessmonitor/issues
