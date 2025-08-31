# DessMonitor Home Assistant Integration

A custom integration to monitor your DessMonitor energy storage system in Home Assistant. 
Updates are periodic: 5 minutes by default, or 1 minute with a DessMonitor premium subscription.

## Quick Setup
1. In Home Assistant: Settings → Devices & Services → Add Integration → "DessMonitor".
2. Enter credentials: Username, Password, Company Key (default is usually correct).
3. Choose Update Interval to match your subscription (5 min default; 1 min premium).

## Key Features
- Multiple inverter support with automatic discovery.
- Sensors for power, voltages, currents, frequency, temperature, load %, operating mode.
- Energy Dashboard compatible (use `*_total_pv_power`, `*_battery_power`, `*_grid_power`).
- Diagnostic sensors available but disabled by default to avoid clutter.

## Manage & Configure
- Change options anytime: Settings → Devices & Services → DessMonitor → Configure.
- Entities follow Home Assistant naming conventions under the `dessmonitor` domain.

## Requirements
- Home Assistant 2024.1.0 or newer.
- DessMonitor account with at least one online device.
- Internet access to `api.dessmonitor.com`.

## Troubleshooting
- Integration not found after install: Restart Home Assistant; ensure files are in `config/custom_components/dessmonitor/`.
- No devices or data: Confirm devices are online in DessMonitor; check HA logs (Settings → System → Logs).
- Sensors not updating: Verify network access and account update interval; review logs for API errors.
- Enable debug logging (configuration.yaml):
  ```yaml
  logger:
    logs:
      custom_components.dessmonitor: debug
  ```

## Notes
- Credentials remain in Home Assistant; tokens auto‑renew (7‑day lifetime).
- Respect DessMonitor API limits; avoid excessively frequent polling.

## Support
- Issues: https://github.com/andreas-glaser/ha-dessmonitor/issues