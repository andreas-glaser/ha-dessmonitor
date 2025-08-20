# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial development in progress

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

[Unreleased]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/andreas-glaser/ha-dessmonitor/releases/tag/v1.0.0