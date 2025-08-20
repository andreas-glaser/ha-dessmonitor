# DessMonitor Home Assistant Integration

This custom integration allows you to monitor your DessMonitor energy storage system directly in Home Assistant.

## Features

- **Real-time monitoring** of multiple inverters
- **Comprehensive sensor data** including power, voltage, current, frequency, temperature
- **Device status tracking** with connectivity monitoring
- **Automatic device discovery** for all inverters on your account
- **UI-based configuration** - no need to edit YAML files
- **Secure authentication** with token-based API access

## Supported Sensors

### Power Monitoring
- Output Power (W)
- Battery Power (W) - positive = charging, negative = discharging
- Solar Power (W)
- Grid Power (W)

### Electrical Measurements
- Output Voltage (V)
- Battery Voltage (V)
- Solar Voltage (V)
- Output Current (A)
- Battery Current (A)
- Solar Current (A)
- Output Frequency (Hz)
- Grid Frequency (Hz)

### System Status
- Load Percentage (%)
- Operating Mode (Off-Grid, Grid, Hybrid)
- Device Connectivity Status
- Inverter Temperature (°C)
- DC Module Temperature (°C)

## Installation

### Method 1: Manual Installation

1. Download the `dessmonitor` folder from this repository
2. Copy it to your Home Assistant `custom_components` directory:
   ```
   <config_directory>/custom_components/dessmonitor/
   ```
3. Restart Home Assistant
4. Go to **Settings** > **Devices & Services**
5. Click **Add Integration** and search for "DessMonitor"

### Method 2: HACS (Recommended)

*Note: This integration is not yet available in HACS. Manual installation is required.*

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "DessMonitor" and select it
3. Enter your DessMonitor credentials:
   - **Username**: Your DessMonitor account username
   - **Password**: Your DessMonitor account password
   - **Company Key**: Leave as default unless specified by your installer
4. Click **Submit** to complete setup

The integration will automatically discover all inverters associated with your account.

## Device Information

Each inverter appears as a separate device in Home Assistant with:
- Device name (e.g., "Inverter 1", "Inverter 2")
- Manufacturer: DessMonitor
- Model: Energy Storage Inverter
- Serial number
- Firmware version

## Automation Examples

### Battery Low Alert
```yaml
automation:
  - alias: "Battery Low Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.inverter_1_battery_voltage
        below: 48
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Battery Low"
          message: "Inverter 1 battery voltage is {{ states('sensor.inverter_1_battery_voltage') }}V"
```

### High Load Notification
```yaml
automation:
  - alias: "High Load Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.inverter_1_load_percentage
        above: 90
    action:
      - service: notify.home_assistant
        data:
          title: "High Load"
          message: "Inverter 1 load is at {{ states('sensor.inverter_1_load_percentage') }}%"
```

### Solar Production Summary
```yaml
automation:
  - alias: "Daily Solar Summary"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Solar Summary"
          message: >
            Total solar power: 
            {% set total = states('sensor.inverter_1_solar_power')|float + 
                          states('sensor.inverter_2_solar_power')|float + 
                          states('sensor.inverter_3_solar_power')|float + 
                          states('sensor.inverter_4_solar_power')|float %}
            {{ total }}W
```

## Energy Dashboard Integration

The power sensors can be integrated into Home Assistant's Energy Dashboard:

1. Go to **Settings** > **Dashboards** > **Energy**
2. Configure your energy sources:
   - **Solar Production**: Add your solar power sensors
   - **Battery Storage**: Add your battery power sensors
   - **Grid Consumption**: Add your grid power sensors

## Troubleshooting

### Authentication Issues
- Verify your username and password are correct
- Check that your account has access to the DessMonitor platform
- Ensure your company key is correct (default is usually fine)

### No Data/Devices Not Found
- Confirm your inverters are online and reporting to DessMonitor
- Check the Home Assistant logs for specific error messages
- Try removing and re-adding the integration

### Connection Problems
- Verify internet connectivity
- Check if the DessMonitor API is accessible from your location
- Review firewall settings that might block outgoing connections

## API Rate Limiting

The integration polls the DessMonitor API every 5 minutes by default to avoid overwhelming the service. This provides a good balance between real-time monitoring and API stability.

## Support

For issues and feature requests, please visit:
- [GitHub Issues](https://github.com/andreas-glaser/ha-dessmonitor/issues)
- [Home Assistant Community Forum](https://community.home-assistant.io/)

## Technical Details

This integration uses the unofficial DessMonitor Open Platform API with:
- SHA-1 signature-based authentication
- Token-based session management (7-day validity)
- RESTful API calls over HTTP
- Automatic token renewal

## License

This project is licensed under the MIT License - see the [LICENSE](../../LICENSE) file for details.

## Disclaimer

This integration is not officially endorsed by DessMonitor. Use at your own risk and ensure compliance with DessMonitor's terms of service.