# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Support for devcode 2451 (Axpert MKS IV 5600VA) with sensor mappings and priority normalization (#5, thanks to @FifoTheHein for the CLI analysis data).

## [1.6.0] - 2025-11-17

### Added
- Documented the `known_inverters` metadata field across device support docs/templates so contributors can record which inverter models have been validated per devcode.
- Device support for devcode 2361 (SRNE SR-EOV24-3.5K-5KWh) with sensor mappings and operating mode normalization (thanks to @pjJedi for the CLI analysis data).
- Additional sensor definitions (inverter current, load apparent power, PV/inverter radiator temperatures, battery energy charge/discharge counters, accumulated mains load energy, daily/total battery amp-hours, etc.) so devcode-specific mappings can surface the extended telemetry in Home Assistant.
- CLI `analyze` command now pulls control-field metadata and live parameter values so contributors can map diagnostics/configuration sensors without manually querying the API.

### Changed
- README device-support section now explicitly lists the confirmed inverter pairing for devcodes 2376 (POW-HVM6.2K-48V-LIP) and 6422 (Must PH19-6048 EXP) and clarifies how the generic fallback behaves.
- DessMonitor API and config flow now mask usernames, passwords, and tokens in logs and drop unused RC4 helper to avoid leaking sensitive data.
- Sensor setup now applies devcode transformations before filtering supported types, preventing SRNE/POW-HVM data from being dropped when titles differ from the canonical names.

### Fixed
- devcode 2361 operating mode mapping now handles the "Inverter Operation" string reported by SRNE SR-EOV24 collectors so the mode appears in Home Assistant (#3).
- Battery Energy Total (Charge/Discharge) sensors use the `measurement` state class to avoid Home Assistant Recorder warnings when devices report occasional counter decreases (#3).

## [1.5.0] - 2025-11-09

### Added
- Support for DessMonitor devcode 6422 used by Must PH19-6048 EXP collectors, including operating-mode normalization (thanks to @tosstosstoss for providing analysis data)
- New sensor definitions (SOC, PV string voltages/currents, accumulated energy counters, radiator temperatures, charger enable state, etc.) so the additional metrics surface in Home Assistant

## [1.4.10] - 2025-11-05

### Fixed
- Prevent entity disappearance during network errors by properly propagating exceptions instead of silently returning empty collector list

## [1.4.9] - 2025-09-30

### Added
- Persistent token caching and refresh mechanism to reduce authentication overhead and improve reliability

### Changed
- Modularized API data flow and diagnostics for improved maintainability

### Fixed
- Deduplicated diagnostic priority sensors to prevent duplicate entity creation

## [1.4.8] - 2025-09-26

### Fixed
- Resolve 500 Internal Server Error during integration configuration that prevented users from setting up the integration
- Remove problematic nested `vol.Schema(lambda)` validators in configuration flow that caused Voluptuous serialization errors
- Move string trimming functionality to validation function to maintain proper input sanitization

## [1.4.7] - 2025-09-25

### Changed
- Documented the requirement to wait for passing CI runs before tagging releases in the commit and release guides.

### Fixed
- Adjusted integration formatting to satisfy linting so the CI pipeline succeeds.

## [1.4.6] - 2025-09-25

### Fixed
- Treat DessMonitor authentication timeouts as retryable `ConfigEntryNotReady` errors so Home Assistant keeps retrying setup instead of failing permanently.
- Handle cancelled aiohttp requests as timeouts in the DessMonitor API client to avoid silent setup crashes.

## [1.4.5] - 2025-09-25

### Changed
- Improved DessMonitor API error logging with detailed HTTP status and response diagnostics for easier troubleshooting of 500 errors.
- Added Git/GitHub workflow guide covering branching, tagging, and release process.

### Fixed
- Normalized operating mode values reported as "Mains Mode" to prevent enum sensor setup failures in Home Assistant.

## [1.4.4] - 2025-09-14

### Added
- CLI: New `sp-keys` command to query SP Key Parameters for a device, with graceful fallbacks and `--raw` output option.
- CLI Docs: Usage section for `sp-keys` with examples and notes.

### Changed
- README: Added "Supported Inverter Brands" section (PowMr, EASUN Power, MPP Solar, MUST Power, Voltronic Axpert rebrands, Fronus Solar) and improved Quick Start HACS link formatting.
- Release Guide: Added practical git log commands and branch sync guidance for preparing changelogs.

### Removed
- Deprecated `custom_components/dessmonitor/device_mappings.py` in favor of `device_support/` devcode-based architecture.

## [1.4.3] - 2025-09-05

### Fixed
- Home Assistant warnings for apparent power sensors by setting device_class to `apparent_power` when unit is `VA` (Output Apparent Power)

### Changed
- Clarified unit/device class handling for apparent power in code comments

## [1.4.2] - 2025-08-31

### Fixed
- **Security Improvements**
  - Switched from HTTP to HTTPS for all API communications
  - Removed sensitive data from debug logs (company keys, full usernames)
  - Added input validation with length limits for config flow fields
- **Code Quality**
  - Resolved all mypy type annotation errors
  - Fixed ConfigFlow domain registration issue
  - Consolidated unit constants into centralized UNITS dictionary
  - Extracted common device info logic to reduce code duplication

### Changed
- **Technical Debt Reduction**
  - Created shared utils module for common functionality
  - Improved exception handling with better context
  - Enhanced input validation for user credentials

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

[Unreleased]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.10...v1.5.0
[1.4.10]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.9...v1.4.10
[1.4.9]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.8...v1.4.9
[1.4.8]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.7...v1.4.8
[1.4.7]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.6...v1.4.7
[1.4.6]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.5...v1.4.6
[1.4.5]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.4...v1.4.5
[1.4.4]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.4.3...v1.4.4
[1.1.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/andreas-glaser/ha-dessmonitor/releases/tag/v1.0.0
