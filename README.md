# DessMonitor Home Assistant Integration

A custom Home Assistant integration for monitoring DessMonitor energy storage systems in real-time.

> **Also known as:** SmartESS, Smart ESS, WatchPower, or other Eybond cloud-based monitoring platforms. This integration works with any inverter system that reports to the DessMonitor web platform (www.dessmonitor.com).

## 🌟 Features

- Real-time monitoring of multiple inverters/collectors
- Comprehensive sensor data**: Power, voltage, current, frequency, temperature, and more
- UI-based configuration - No YAML editing required
- Automatic device discovery for all inverters on your account
- Configurable update intervals (1-60 minutes based on your subscription)
- Secure token-based authentication with automatic restar7-day renewal
- Energy Dashboard integration for production/consumption tracking
- Smart device naming with PN identifiers for easy identification

## 📊 Available Sensors

### Power Monitoring
- **Output Power** (W) - Current inverter output
- **Battery Power** (W) - Charging/discharging power (+ = charging, - = discharging)  
- **Solar Power** (W) - Current solar panel generation
- **Grid Power** (W) - Grid import/export power

### Electrical Measurements
- **Voltages** (V) - Output, Battery, Solar voltages
- **Currents** (A) - Output, Battery, Solar currents
- **Frequencies** (Hz) - Output and Grid frequency monitoring

### System Status
- **Load Percentage** (%) - Current system load
- **Operating Mode** - Off-Grid, Grid, or Hybrid mode
- **Device Connectivity** - Online/offline status
- **Temperatures** (°C) - Inverter and DC module temperatures

## 🚀 Installation

### Method 1: HACS (Recommended)

1. **Install HACS** if you haven't already
2. **Add Custom Repository**:
   - Go to HACS > Integrations > ⋮ > Custom repositories
   - Add: `https://github.com/andreas-glaser/ha-dessmonitor`
   - Category: Integration
3. **Install**: Search for "DessMonitor" and install
4. **Restart** Home Assistant
5. **Configure**: Settings > Devices & Services > Add Integration > "DessMonitor"

### Method 2: Manual Installation

1. **Download** the `custom_components/dessmonitor` folder
2. **Copy** to your Home Assistant `config/custom_components/` directory
3. **Restart** Home Assistant
4. **Configure**: Settings > Devices & Services > Add Integration > "DessMonitor"

## ⚙️ Configuration

### Initial Setup

1. Navigate to **Settings** > **Devices & Services**
2. Click **Add Integration** and search for "DessMonitor"
3. Enter your credentials:
   - **Username**: Your DessMonitor account username
   - **Password**: Your DessMonitor account password
   - **Company Key**: Leave default unless specified by installer
   - **Update Interval**: Choose based on your subscription:
     - **1 minute**: Premium accounts with paid faster updates
     - **5 minutes**: Standard free accounts (default)
     - **10+ minutes**: Reduced frequency options

### Changing Settings Later

You can modify the update interval anytime:
1. Go to **Settings** > **Devices & Services**
2. Find your DessMonitor integration
3. Click the **Configure** button (gear icon)
4. Adjust settings and click **Submit**

## 🔧 Advanced Configuration

### Energy Dashboard Integration

To add DessMonitor data to Home Assistant's Energy Dashboard:

1. Navigate to **Settings** > **Dashboards** > **Energy**
2. Configure energy sources:
   - **Solar Production**: Add your `*_solar_power` sensors
   - **Battery Storage**: Add your `*_battery_power` sensors
   - **Grid Consumption**: Add your `*_grid_power` sensors

### Automation Examples

#### Battery Low Alert
```yaml
automation:
  - alias: "DessMonitor Battery Low Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.inverter_1_test001234567890_battery_voltage
        below: 48
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "⚠️ Battery Low"
          message: "Battery voltage: {{ states('sensor.inverter_1_test001234567890_battery_voltage') }}V"
```

#### High Load Notification
```yaml
automation:
  - alias: "DessMonitor High Load Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.inverter_1_test001234567890_load_percentage
        above: 90
    action:
      - service: notify.persistent_notification
        data:
          title: "🔥 High Load Warning"
          message: "System load at {{ states('sensor.inverter_1_test001234567890_load_percentage') }}%"
```

#### Daily Solar Summary
```yaml
automation:
  - alias: "DessMonitor Daily Solar Summary"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "☀️ Today's Solar Production"
          message: |
            Total solar power: 
            {%- set ns = namespace(total=0) -%}
            {%- for entity_id in states.sensor -%}
              {%- if 'solar_power' in entity_id.entity_id and 'dessmonitor' in entity_id.entity_id -%}
                {%- set ns.total = ns.total + (entity_id.state | float(0)) -%}
              {%- endif -%}
            {%- endfor -%}
            {{ ns.total }}W across all inverters
```

## 🛠️ Troubleshooting

### Common Issues

**Integration not found after installation**
- Ensure files are in `config/custom_components/dessmonitor/`
- Restart Home Assistant completely
- Check logs for any error messages

**Authentication failures**
- Verify username and password are correct
- Ensure your account has access to the DessMonitor web portal
- Check that company key matches your installer's specification

**No devices or sensors appearing**
- Confirm your inverters are online and reporting to DessMonitor
- Check Home Assistant logs: Settings > System > Logs
- Try removing and re-adding the integration

**Sensors not updating**
- Check your network connectivity to api.dessmonitor.com
- Verify your account subscription supports your chosen update interval
- Review integration logs for specific error messages

### Debug Logging

To enable detailed logging for troubleshooting:

```yaml
# configuration.yaml
logger:
  logs:
    custom_components.dessmonitor: debug
```

## 📋 Requirements

- **Home Assistant** 2024.1.0 or newer
- **DessMonitor account** with active inverter(s)
- **Internet connection** to api.dessmonitor.com
- **Python aiohttp** 3.8.0+ (installed automatically)

## 🔒 Security & Privacy

- **Secure authentication** with SHA-1 signature-based tokens
- **Local credential storage** - passwords never leave your Home Assistant
- **7-day token lifecycle** with automatic renewal
- **Rate limiting respect** to avoid API overuse
- **No data collection** - integration only communicates with DessMonitor API

## 🤝 Contributing

Contributions are welcome! Please feel free to:

- **Report bugs** via [GitHub Issues](https://github.com/andreas-glaser/ha-dessmonitor/issues)
- **Request features** for additional sensor types or functionality
- **Submit pull requests** for improvements or bug fixes
- **Improve documentation** with better examples or translations

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This integration is **not officially endorsed** by DessMonitor. It uses reverse-engineered API calls for personal use only. Please:

- **Respect DessMonitor's terms of service**
- **Use reasonable update intervals** to avoid API overload
- **Report any issues** that might affect DessMonitor's service

## 🙏 Acknowledgments

- **DessMonitor** for providing the energy storage hardware and API
- **Home Assistant** community for the excellent platform and development tools
- **Contributors** who help improve and maintain this integration

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/andreas-glaser/ha-dessmonitor/issues)
- **Discussions**: [Home Assistant Community](https://community.home-assistant.io/)

**Enjoying this integration?** ⭐ Star the repository to show your support!