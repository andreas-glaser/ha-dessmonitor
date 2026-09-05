# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- GitHub Actions workflows now use the Node.js 24-compatible `actions/checkout@v7` and `actions/setup-python@v7` releases, removing Node.js 20 deprecation warnings from CI.
- Local discovery now distinguishes timeouts, empty responses, unsupported commands, CRC failures, and transport-header mismatches. Debug logs include bounded per-query routing and timing evidence without response payloads. CLI probes save private diagnostic reports on runtime failure as well as success (#32).

## [2.3.0] - 2026-08-31

### Added
- Optional read-only local telemetry for EyeBond-compatible collectors, with cloud-only, local-only, and preferred-local hybrid modes. Hybrid mode keeps the DessMonitor API as the canonical source for identity, metadata, controls, and fallback data while overlaying faster local readings from one or more explicitly pinned private addresses (#27, thanks to @albertdb for proposing local and hybrid support).
- Guided local configuration, independent cloud/local polling intervals, source diagnostics, persisted cloud snapshots, automatic local reconnect and cloud fallback, and CLI discovery/probing tools with redacted evidence output.

### Changed
- Entity discovery and control loading now recover after delayed cloud availability without duplicating entities. Existing cloud entries, entity identities, recorder history, and cloud-backed controls remain compatible when local telemetry is enabled or disabled.
- Local telemetry startup logs now state the configured polling interval. A collector that does not connect within two minutes produces a clear warning covering the outbound UDP callback request, inbound TCP telemetry connection, and host or VLAN firewall rules.
- Local setup guidance now documents both network directions, recommends source-restricted firewall access, and includes a commented UFW example. Callback retries remain independent from the configured telemetry polling interval.

### Fixed
- Numeric voltage/current controls with missing or contradicted API range hints no longer derive a moving range from the value cached at startup. They now use a stable fallback, switch to box input, and widen for unusually large live values, preventing Home Assistant from rejecting valid changes before they reach DessMonitor. Numeric controls also refresh their state from the regular polled payload when available, so changes made in DessMonitor or the mobile app no longer require an integration reload (#30, thanks to @blihtar for tracing the stale-value behaviour and verifying the affected inverter's hardware limits).
- Fast local updates no longer postpone the independent cloud refresh timer. Hybrid mode retains per-device cached cloud data through vendor timeouts while healthy local collectors continue updating, and stale local tunnels are recycled into targeted reconnect attempts.
- Release packaging now keeps the API client's internal version aligned with `VERSION` and the integration manifest, preventing packaged releases from identifying themselves as the previous stable version.

## [2.2.0] - 2026-06-20

### Added
- Test suite: introduced a `pytest` suite under `tests/` running against a real Home Assistant core via `pytest-homeassistant-custom-component` (pinned in `requirements_test.txt`, configured in `pyproject.toml`). Covers the config-flow update-interval coercion (#29) and the number-entity slider range/step logic (#22/#23), with the latter at 100% line coverage. Run with `make test` / `make test-cov`; `make install` now also installs the test dependencies.
- CLI: `analyze` output now captures `hint` (e.g. `"48.0~56.0V"`) and `unit` for value-type control fields, so contributors debugging number-entity range issues have the API-provided min/max available directly in the analysis JSON. Bumped `analysis_version` to 3; existing v2 analyses still verify against their own checksum (#22, thanks to @arasuludag for the detailed bug report that exposed the gap).

### Fixed
- Charging-voltage and current number entities now stay usable when the DessMonitor API sends a wrong or missing `hint`. The slider range used to come straight from the hint, so a bad hint (e.g. `25-30V` reported on a 48V system whose live setting is `57.6V`) or a missing hint (HA defaulting to `0-100`) left the slider unusable and rejected valid `number.set_value` calls as "out of range". The range is now trusted only when the hint actually brackets the device's current value; otherwise it is synthesized around the live value (floored at `0` for V/A, generous headroom). Since the API rejects genuinely invalid writes, erring wide is safe. The range logic moved to a dependency-free `number_range.py` helper (#22, thanks to @arasuludag for confirming the API returns the wrong hint and @albertdb for the 12V data point and the "API rejects invalid writes anyway" insight; also resolves the range half of #23 reported by @Dymyk).
- Unloading a config entry no longer raises `KeyError` if the coordinator was never stored (e.g. when setup failed partway): `async_unload_entry` now pops from `hass.data` defensively and only closes the API session when a coordinator is present.
- Config flow: selecting an update interval no longer fails with `value must be one of [60, 300, 600, 1800, 3600]` on submit. The interval dropdown is backed by an integer-keyed `vol.In`, but the frontend returns the chosen value as a string, so validation rejected every selection and the integration could not be added. The schema now coerces the value to `int` before the membership check (`vol.All(vol.Coerce(int), vol.In(...))`) in both the initial setup and the options flow, mirroring Home Assistant core's own idiom (#29, thanks to @Obibokhomie for the detailed report and root-cause analysis, and to @mullerpetr76 and @Rybriz for confirming).
- Voltage and current number entities (e.g. bulk/floating charging voltage, max charging current) now get a `0.1` step even when the DessMonitor API omits the `hint` field for that control. Previously the step was only set when a hint was present, so hint-less fields fell back to Home Assistant's default step of `1`, making the slider too coarse for voltage adjustments (#23, thanks to @Dymyk for the screenshot showing the entity attributes).

## [2.1.0] - 2026-04-20

### Added
- Support for devcode 2507 (ANENJI ANJ-6200W-48PL-WIFI) with sensor title mappings for Battery SOC, energy totals, and temperature titles with API typos and double spaces. Operating mode normalisation fixes the "Grid mode" value so the Operating Mode sensor is available, and output/charger priority mappings cover the short codes returned by the collector (#21, thanks to @algrishina for the CLI analysis data).

### Fixed
- devcode 2452 (Axpert PI18): duplicate `Energy Today` / `Energy Total` entities caused by the summary endpoint (`webQueryDeviceEs`) returning `energyToday`/`energyTotal` alongside the lastData-sourced `Today/Total generation`; both are now mapped to the canonical names so the coordinator's summary-dedup logic skips them (#17, thanks to @DastardlyBaker for the HA screenshots and analysis data).
- devcode 2452 (Axpert PI18): `Energy Today`, `Energy Month`, and `Energy Year` values were inflated ~1000x because `queryDeviceLastData` reports these counters in Wh while the sensor unit is fixed to kWh; values are now scaled to kWh. `Total generation` is already reported in kWh and is left unchanged (#17).

### Changed
- Documentation: added a contributor guide in `custom_components/dessmonitor/device_support/README.md` covering the end-to-end devcode onboarding workflow (CLI analysis, mapping file layout, registry registration, and changelog conventions) so new devcode contributions can be prepared without reading the existing devcode files as examples.

## [2.0.0] - 2026-04-18

### Added
- **Device configuration control** - Read and write inverter settings directly from Home Assistant (#16, #18). All controllable fields are dynamically discovered from the DessMonitor API per device:
  - **Select entities** for settings with predefined options (Output Priority, Charger Source Priority, Battery Type, Buzzer Mode, Output Voltage/Frequency, Boot Method, and more).
  - **Number entities** for numeric settings with min/max ranges parsed from the API hint field (charging voltages, max currents, SOC protection values, EQ timers).
  - **Button entities** for single-action commands (Clear Record, Reset User Settings, Forced EQ Charging, Exit Fault Mode) - dynamically detected from API fields with exactly one option.
  - Current values are read from all devices in parallel at startup via `queryDeviceCtrlValue` and cached. Writes update the cache optimistically.
- Support for devcode 2452 (Axpert PI18 protocol, rebranded) with sensor mappings, output/charger priority normalization, and dual PV input / second AC output support (#17, thanks to @DastardlyBaker for the CLI analysis data).
- Support for devcode 2428 (Hybrid inverter) with sensor title mappings for output power/voltage/frequency, battery capacity to State of Charge, PV charging current/voltage, and load percent (#20, thanks to @KIBkz for the CLI analysis data).
- New sensor definitions: Energy Month, Energy Year, Second Output Frequency, Second Output Voltage.
- CLI: analysis output now includes `analysis_version` field (v2) and HMAC-SHA256 `checksum` for integrity verification. Device serial number is excluded from the checksum so users can redact it without breaking validation.
- CLI: new `verify` command to validate analysis JSON files against their checksum.

## [1.9.0] - 2026-03-01

### Added
- Support for devcode 6515 (ANENJI ANJ-HHS-11KW-48V-WIFI) with sensor mappings, operating mode normalization, and PV temperature support (#13, thanks to @dekov3 for the CLI analysis data).
- Support for devcode 6544 (ANENJI ANJ-HHS-11KW-48V) with sensor mappings, operating mode normalization, and split-phase output support (#11, thanks to @blihtar for the CLI analysis data).

### Fixed
- Fetch "Battery percentage" (SOC) from the parameters API endpoint for devcode 2376, since this sensor only exists in `queryDeviceParsEs` and not in `queryDeviceLastData`. The coordinator now fetches parameters in parallel when a devcode declares `parameter_sensor_names`, merges them with dedup into the device data, and the existing title mapping produces the State of Charge entity (#12, thanks to @baziliolg for reporting and providing analysis data).
- Graceful per-device error handling: a single device returning `ERR_NO_RECORD` (API error 12) no longer blocks all other devices from loading. Failed devices are skipped with a warning log, and `UpdateFailed` is only raised when every collector fails.

## [1.8.0] - 2026-01-28

### Added
- Support for devcode 2334 (EASUN 6.2KW Hybrid Solar Inverter) with sensor mappings and priority normalization (#8, thanks to @AndyTempleman for the CLI analysis data).
- Support for devcode 2449 (EASUN 8/11KWA, WKS Evo MAX II 10kVA 48V) with sensor mappings, priority normalization, and operating mode handling (#6, thanks to @TheJudge01 and @mielune for the CLI analysis data).
- New sensor definitions: Battery Charging Current, Battery Discharge Current, State of Charge, Output Frequency, Energy Today, Energy Total.

### Fixed
- Standardized sensor title casing across all devcode files (Output Frequency, State of Charge, Energy Today/Total now have proper SENSOR_TYPES metadata).
- Resolved mypy type errors in data coordinator for devcode type narrowing.

## [1.7.0] - 2025-12-11

### Added
- Support for devcode 2451 (Axpert MKS IV 5600VA) with sensor mappings and priority normalization (#5, thanks to @FifoTheHein for the CLI analysis data).

### Fixed
- Treat placeholder string values (e.g., "-"/"n/a") as unavailable so HA numeric sensors don't raise errors when PV readings are missing.
- Deduplicate summary energy sensors by mapping titles, preventing duplicate Energy Today/Total entities when summary data overlaps with device data.
- Lower duplicate sensor log level to DEBUG to reduce noise when duplicate titles are safely skipped.

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

[Unreleased]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v2.3.0...HEAD
[2.3.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.9.0...v2.0.0
[1.9.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/andreas-glaser/ha-dessmonitor/compare/v1.6.0...v1.7.0
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
