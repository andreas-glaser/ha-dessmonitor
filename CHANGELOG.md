# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Future development in progress

## [1.1.0] - 2025-08-21

### Added
- **Diagnostic sensors** for battery and inverter configuration monitoring
  - Output Priority sensor (SBU/SUB/UTI/SOL settings)
  - Charger Source Priority sensor (PV First/Utility First/etc.)
  - Output Voltage Setting sensor (configured voltage target)
- **Energy tracking sensors** for better Home Assistant Energy Dashboard integration
  - Total PV Power (kW) - real-time solar output per inverter
  - Energy Today (kWh) - daily energy production per inverter
  - Energy Total (kWh) - lifetime energy production per inverter
- **Additional measurement sensors**
  - AC Charging Power and Current
  - PV Charging Power and Current
  - Output Apparent Power (VA)
- **Device diagnostics support** for advanced troubleshooting
- **Comprehensive documentation** with automation examples and diagnostic sensor usage

### Changed
- **Diagnostic sensors are disabled by default** to keep dashboards clean
- **Improved README** with detailed sensor descriptions and setup instructions
- **Enhanced API data processing** to support summary/total sensors from webQueryDeviceEs
- **Better device naming** and sensor organization

### Technical
- **New diagnostics.py platform** for configuration sensors (disabled by default)
- **Extended API client** with device summary data and control field support
- **Improved data coordinator** with control field caching and summary data integration
- **Enhanced sensor mapping** for text-based sensors (enum device class support)
- **Code cleanup** - removed all comment lines for cleaner codebase

## [1.0.0] - 2025-08-20

### Added
- Initial release of DessMonitor Home Assistant integration
- Support for multiple inverter/collector monitoring
- Real-time sensor data: power, voltage, current, frequency, temperature
- UI-based configuration with Home Assistant config flow
- Automatic device discovery via DessMonitor API
- Configurable update intervals (1-60 minutes)
- Secure token-based authentication with 7-day renewal
- Binary sensors for device status and operating mode
- Energy Dashboard integration compatibility
- Comprehensive error handling and logging
- Support for device naming with PN identifiers
- Duplicate sensor prevention
- HACS marketplace compatibility

### Technical
- SHA-1 signature-based API authentication
- Pagination support for multi-device discovery
- Async/await architecture for Home Assistant compatibility
- Complete GitHub Actions CI/CD pipeline
- Code quality enforcement (Black, isort, flake8)
- Hassfest and HACS validation

[Unreleased]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/andreas-glaser/ha-dessmonitor/releases/tag/v1.0.0