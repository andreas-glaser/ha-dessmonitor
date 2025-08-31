# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Future development in progress

## [1.4.1] - 2025-08-31

### Changed
- **Documentation Updates**
  - Clarified update intervals are periodic, not real-time
  - Added "Detailed Data Collection Acceleration" subscription details (￥144 per collector)
  - Updated repository description to mention solar inverters instead of energy storage
  - Added Energy-Mate and Fronus Solar to list of compatible apps
  - Improved clarity on 1-minute update requirements

## [1.4.0] - 2025-08-29

### Added
- **Brand Assets** for improved HACS integration visibility
- **Screenshots Section** with visual documentation of the integration

### Changed
- **Documentation Improvements**
  - Enhanced README with quick start guide
  - Improved structure and navigation
  - Added visual examples with screenshots

## [1.3.1] - 2025-08-25

### Fixed
- **Release Workflow** ZIP file naming mismatch with hacs.json - now correctly creates `ha-dessmonitor.zip` for HACS compatibility

## [1.3.0] - 2025-08-24

### Added
- **Enhanced CLI Tool Features**
  - Device data fallback for devices not in collectors
  - DevCode template generation with `--template` flag
  - Automatic typo detection in sensor names
  - Sensor pattern analysis (units, priorities, operating modes)
  - Debug mode with `--debug` flag for verbose logging
  - Raw JSON output with `--raw` flag for all commands
- **HACS Repository Support**
  - Complete hacs.json configuration for HACS submission
  - Status badges in README (Release, Activity, License, HACS, Hassfest)
  - One-click HACS repository installation button
  - GitHub Actions validation for HACS and Hassfest

### Changed
- **Documentation Improvements**
  - Added visual status badges to README
  - Enhanced installation instructions with HACS button
  - Updated metadata for better HACS discovery

### Fixed
- **CLI Tool** inverter online/offline status display (status=0 means online)
- **HACS Validation** country code configuration (using ALL for worldwide)

## [1.2.0] - 2025-08-24

### Added
- **DessMonitor CLI Tool** for device analysis and development (`tools/cli/`)
  - Device discovery and analysis commands
  - Real-time sensor data querying
  - DevCode analysis for creating device support configurations
  - Comprehensive documentation for contributors
- **Device Support Architecture** with extensible DevCode system
  - Automatic device classification by DevCode
  - Device-specific sensor name and value mappings
  - Support for DevCode 2376 with complete transformations
  - Template system for adding new device support
- **Docker Development Environment** (`tools/docker/`)
  - Pre-configured Home Assistant development setup
  - Auto-mounted custom components for testing
  - Easy integration testing workflow
- **Enhanced Documentation**
  - Complete CLI tool usage guide
  - Device support contribution workflow
  - Development environment setup instructions

### Changed
- **API Version Update** to 1.1.0 for improved compatibility
- **Integration Architecture** now supports device-specific transformations
- **Sensor Creation** process enhanced with DevCode-based mappings
- **Operating Mode Options** now dynamically generated from device mappings

### Fixed
- **Code Quality** improvements with resolved linting issues
- **Import Optimization** removed unused imports across modules

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