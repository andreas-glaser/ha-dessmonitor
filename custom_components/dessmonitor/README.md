# DessMonitor Home Assistant Integration

A custom integration to monitor and control your DessMonitor solar inverter system in Home Assistant.
Updates are periodic: 5 minutes by default, or 1 minute with Detailed Data Collection Acceleration (￥144 per collector).

## Quick Setup
1. In Home Assistant: Settings > Devices & Services > Add Integration > "DessMonitor".
2. Enter credentials: Username, Password, Company Key (default is usually correct).
3. Choose Update Interval:
   - 5 minutes: Standard rate (recommended)
   - 1 minute: Requires "Detailed Data Collection Acceleration" from DessMonitor

## Key Features
- Multiple inverter support with automatic discovery.
- Sensors for power, voltages, currents, frequency, temperature, load %, operating mode.
- Energy Dashboard compatible (use `*_total_pv_power`, `*_battery_power`, `*_grid_power`).
- Device configuration via select, number, and button entities (output priority, charger source, battery settings, buzzer mode, and more).
- Supported devcodes: 2334, 2361, 2376, 2428, 2449, 2451, 2452, 6422, 6515, 6544.
- Diagnostic sensors available but disabled by default to avoid clutter.

## Device Configuration

The integration exposes inverter settings as Home Assistant entities, allowing you to read and change device configuration directly from your dashboard or automations.

- **Select entities**: Settings with predefined options (output priority, charger source priority, battery type, buzzer mode, etc.)
- **Number entities**: Numeric settings with min/max ranges from the device (charging voltages, max currents, SOC protection values, EQ timers, etc.)
- **Button entities**: One-shot actions (clear record, reset user settings, forced EQ charging, exit fault mode)

All current values are read from the device at startup. Changes take effect immediately via the DessMonitor cloud API.

## Manage & Configure
- Change options anytime: Settings > Devices & Services > DessMonitor > Configure.
- Entities follow Home Assistant naming conventions under the `dessmonitor` domain.

## Requirements
- Home Assistant 2024.1.0 or newer.
- DessMonitor account with at least one online device.
- Internet access to `api.dessmonitor.com`.

## Troubleshooting
- Integration not found after install: Restart Home Assistant; ensure files are in `config/custom_components/dessmonitor/`.
- No devices or data: Confirm devices are online in DessMonitor; check HA logs (Settings > System > Logs).
- Sensors not updating: Verify network access and account update interval; review logs for API errors.
- Configuration entities showing blank: Integration reads all control values at startup; if the API is slow, some values may time out. Restart HA to retry.
- Enable debug logging (configuration.yaml):
  ```yaml
  logger:
    logs:
      custom_components.dessmonitor: debug
  ```

## Notes
- Credentials remain in Home Assistant; tokens auto-renew (7-day lifetime).
- Respect DessMonitor API limits; avoid excessively frequent polling.
- Control values are cached at startup and updated optimistically after writes. Restart HA to re-read values from the device.

## Support
- Issues: https://github.com/andreas-glaser/ha-dessmonitor/issues
