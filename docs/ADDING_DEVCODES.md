# Adding a New Devcode

This guide walks a contributor through adding support for a new DessMonitor data collector (devcode). Follow it end to end when a user reports that their inverter shows up as "Unsupported Device (devcode NNNN)" in Home Assistant, or when they submit a CLI analysis for an unknown devcode.

## Background

- The **devcode** identifies the *data collector / gateway* (the WiFi/4G dongle that talks to the DessMonitor cloud), not the inverter itself. The same inverter family can ship with different collectors, and the same collector can be rebranded across several inverter brands.
- Each supported devcode has a file `custom_components/dessmonitor/device_support/devcode_XXXX.py` that tells the integration how to translate that collector's API output into canonical sensor names, operating modes, and priority labels.
- The registry in `device_support/device_registry.py` imports every devcode module and is consulted by the sensor platform via `apply_devcode_transformations()` in the coordinator.
- Unknown devcodes still work through a generic fallback (raw titles and values, no enum mapping), so the goal of adding a devcode is to clean up names, normalise enum values, and expose sensors that the API hides behind verbose or typo-laden titles.

## Prerequisites

- The reporter's DessMonitor credentials (`username`, `password`, `company_key`) OR a `analysis.json` file they produced with the CLI tool.
- Python 3.7+ with `pip install -r tools/cli/requirements.txt`.
- A local checkout of the `dev` branch.

## Workflow Overview

```
1. Reporter produces analysis.json with the CLI
2. Verify analysis.json integrity (checksum)
3. Read the analysis and pick mappings
4. Write devcode_XXXX.py following the sibling pattern
5. Register in device_registry.py
6. Update README.md, device_support/README.md, CHANGELOG.md
7. Run lint/type/format checks
8. Commit and push; open a PR that references the issue and credits the reporter
```

## 1. Produce the analysis (contributor side)

Ask the reporter to run:

```bash
cd tools/cli
pip install -r requirements.txt
python3 dessmonitor_cli.py auth \
    --username USER --password PASS --company-key KEY

python3 dessmonitor_cli.py collectors
python3 dessmonitor_cli.py devices --pn COLLECTOR_PN
python3 dessmonitor_cli.py analyze \
    --device-sn DEVICE_SN --output analysis_XXXX.json
```

The `analyze` command writes a structured JSON file containing sensor titles, observed operating mode / priority values, unit patterns, a sample of live data, device control fields, and an HMAC checksum. The reporter should attach that file to the GitHub issue or PR.

## 2. Verify the analysis file

Integrity check, so you know the JSON has not been edited after generation:

```bash
python3 tools/cli/dessmonitor_cli.py verify /path/to/analysis_XXXX.json
```

Expected output: `Checksum OK - analysis data is intact.` (A v1 analysis without a checksum is acceptable but older; prefer v2.)

The device SN is excluded from the checksum so reporters can redact it without breaking validation.

## 3. Read the analysis

Open the analysis and note these fields under the `analysis` key:

| Field | What to do with it |
|-------|--------------------|
| `devcode` | The number you will use for the filename (`devcode_XXXX.py`) and registry entry |
| `collector_alias` | Hint about the inverter brand |
| `operating_modes` | All mode strings the collector has emitted; map any that do not match the canonical `OPERATING_MODES` list |
| `output_priorities` | Values seen from "Current output priority" / "Output priority" sensors |
| `charger_priorities` | Values seen from "Current charging priority" / "Charger Source Priority" sensors |
| `sensor_titles` | Raw API titles; compare against `SENSOR_TYPES` in `const.py` |
| `potential_typos` | Titles the CLI flagged as likely typos |
| `unit_patterns` | Shows which titles returned non-numeric strings (icon-state sensors, etc.) |
| `control_fields` | Authoritative enum of priority/config codes the inverter supports, e.g. `{"1":"SUB","2":"SBU","3":"SUF","4":"ZEC"}` |
| `parameter_count` / `parameters` | Sensors only returned by `queryDeviceParsEs`, not by `queryDeviceLastData` |

Also ask the reporter for the inverter model and manufacturer so you can populate `known_inverters`.

## 4. Create `devcode_XXXX.py`

Copy `custom_components/dessmonitor/device_support/devcode_template.py` to `devcode_XXXX.py` and fill in each section. The **sibling pattern** is the source of truth: pick the most similar existing file (same brand, same form factor) and match its style closely. Good recent references:

- `devcode_6515.py` / `devcode_6544.py` — ANENJI WiFi / split-phase
- `devcode_2428.py` — minimal hybrid with only title mappings
- `devcode_2452.py` — Axpert PI18 with value transformations (Wh→kWh)
- `devcode_2451.py` — Axpert MKS IV with long-form priority values

### 4.1 `DEVICE_INFO`

```python
DEVICE_INFO = {
    "name": "DessMonitor Data Collector (devcode XXXX)",
    "description": "DessMonitor data collector/gateway",
    "manufacturer": "DessMonitor",
    "known_inverters": ["Brand Model X"],
    "supported_features": [
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}
```

Only list features the collector actually exposes.

### 4.2 `OUTPUT_PRIORITY_MAPPING` and `CHARGER_PRIORITY_MAPPING`

Use the `control_fields` section of the analysis as the authoritative enum. If the collector uses short codes (`SUB`, `SBU`, `SOF`), map them to readable labels consistent with sibling devcodes. Do NOT import mappings from unrelated devcodes as "fallbacks" — each devcode is a standalone contract.

Example (ANENJI-style short codes):

```python
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "SUB": "Solar → Utility → Battery",
    "SBU": "Solar → Battery → Utility",
    "SUF": "Solar → Utility First",
}

CHARGER_PRIORITY_MAPPING: dict[str, str] = {
    "SOF": "Solar First",
    "SNU": "Solar and Utility",
    "OSO": "Only Solar",
    "SOR": "Solar or Utility",
}
```

Example (Axpert long-form values that need normalising, from `devcode_2452.py`):

```python
OUTPUT_PRIORITY_MAPPING: dict[str, str] = {
    "Solar-Utility-Battery": "Solar → Utility → Battery",
    "Solar-Battery-Utility": "Solar → Battery → Utility",
}
```

### 4.3 `OPERATING_MODE_MAPPING`

Canonical `OPERATING_MODES` (in `const.py`):

```
Power On, Standby, Line, Battery, Fault, Shutdown Approaching,
Off-Grid Mode, Grid Mode, Hybrid Mode, Unknown
```

The Home Assistant enum sensor marks any value outside this list as `unavailable` UNLESS the devcode's `OPERATING_MODE_MAPPING` registers it. `get_all_operating_modes()` dynamically extends the enum with both the keys and values of every devcode's mapping, so you can either:

- Map a collector-specific value to a canonical one (e.g. `"Grid mode": "Grid Mode"` fixes a casing issue), or
- Map a collector-specific value to a new label that you want to expose as-is (e.g. `"Inverter Mode": "Off-grid Mode"`).

Only list modes that are either (a) observed in the analysis, or (b) documented in the inverter manual and likely to appear.

### 4.4 `SENSOR_TITLE_MAPPINGS`

The sensor-resolution pipeline in `sensor.py` already tries:

1. Exact match against `SENSOR_TYPES` keys
2. Case-insensitive, whitespace-stripped match against `SENSOR_TYPES` keys
3. Case-insensitive, whitespace-stripped match against each entry's friendly `name`

Only add a mapping when a raw API title would fail all three. Common cases:

- **Verbose names**: `"Daily PV energy generation"` → `"Energy Today"`
- **Double spaces / typos that break the normaliser**: `"DCDC  module Termperature"` → `"DC Module Temperature"`
- **Exposing hidden sensors**: `"Battery SOC"` → `"State of Charge"`, `"Battery Capacity"` → `"State of Charge"`
- **Duplicate-title dedup for the summary endpoint**: map alternate names (`"energyToday"`, `"Today generation"`) to the same canonical key so the coordinator's dedup logic skips them.

A title that already resolves automatically (e.g. `"PV temperature"` → `"PV Temperature"` via the normaliser) does NOT need a mapping. Keep the dict minimal.

### 4.5 `VALUE_TRANSFORMATIONS`

Use when the API delivers a value in the wrong unit or with wrong scaling. Keys are the *post-title-mapping* title (the canonical name), values are callables.

Example from `devcode_2452.py`:

```python
def _wh_to_kwh(value):
    try:
        return float(value) / 1000
    except (TypeError, ValueError):
        return value

VALUE_TRANSFORMATIONS: dict = {
    "Energy Today": _wh_to_kwh,
    "Energy Month": _wh_to_kwh,
    "Energy Year": _wh_to_kwh,
}
```

Callables must be tolerant of unparseable input and return something the sensor can display (the original value is a safe fallback).

### 4.6 `PARAMETER_SENSOR_NAMES`

Most sensors arrive via `queryDeviceLastData`. A minority (notably SOC on devcode 2376) only appear under `queryDeviceParsEs`. The analysis lists these in the `parameters` section.

If a needed sensor is *missing* from `sensor_titles` but present in `parameters`, add its raw parameter `name` here:

```python
PARAMETER_SENSOR_NAMES: set[str] = {"Battery percentage"}
```

The coordinator will fetch `queryDeviceParsEs` in parallel and merge the parameters into the device data (deduplicated). Leave empty otherwise.

### 4.7 Footer (do not modify)

```python
DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
}
```

## 5. Register the devcode

Append to `device_support/device_registry.py` inside `_load_device_configurations()`:

```python
from .devcode_XXXX import DEVCODE_CONFIG as config_XXXX

_register_devcode(XXXX, config_XXXX)
```

Match the surrounding style (blank line between each import/register pair).

## 6. Update documentation and changelog

Three files to edit:

1. `README.md` — add a bullet under `### Current Device Support`:
   ```markdown
   - **DevCode XXXX**: Known to pair with Brand Model X
   ```
2. `custom_components/dessmonitor/device_support/README.md` — add the same bullet under `## Currently Supported Collectors`.
3. `CHANGELOG.md` — add an entry under `## [Unreleased]` → `### Added`:
   ```markdown
   - Support for devcode XXXX (Brand Model X) with <one-line summary of mappings> (#NN, thanks to @contributor for the CLI analysis data).
   ```
   Create the `### Added` section if `[Unreleased]` does not already have one.

## 7. Quality checks

```bash
python3 -m black custom_components/dessmonitor
python3 -m isort custom_components/dessmonitor
python3 -m flake8 custom_components/dessmonitor --max-line-length=127
python3 -m mypy custom_components/dessmonitor --ignore-missing-imports
```

Or `make check`.

Smoke-test the registration without spinning up Home Assistant:

```bash
cd custom_components/dessmonitor/device_support
python3 -c "
import importlib.util, sys, types
pkg = types.ModuleType('dessmonitor'); pkg.__path__ = ['../.']
sys.modules['dessmonitor'] = pkg
spec = importlib.util.spec_from_file_location('dessmonitor.const', '../const.py')
mod = importlib.util.module_from_spec(spec); sys.modules['dessmonitor.const'] = mod; spec.loader.exec_module(mod)
ds = types.ModuleType('dessmonitor.device_support'); ds.__path__ = ['.']
sys.modules['dessmonitor.device_support'] = ds
spec = importlib.util.spec_from_file_location('dessmonitor.device_support.device_registry', 'device_registry.py')
reg = importlib.util.module_from_spec(spec); sys.modules['dessmonitor.device_support.device_registry'] = reg; spec.loader.exec_module(reg)
print(sorted(reg.get_supported_devcodes()))
print(reg.map_operating_mode(XXXX, 'observed_mode_value'))
print(reg.map_sensor_title(XXXX, 'Observed Title'))
"
```

Replace `XXXX` and the sample inputs with the real devcode and a handful of observed values to confirm that mappings resolve as expected.

## 8. Commit and push

Match the existing history (see `git log --oneline --grep=devcode`):

```bash
git checkout dev
git add custom_components/dessmonitor/device_support/devcode_XXXX.py \
        custom_components/dessmonitor/device_support/device_registry.py \
        custom_components/dessmonitor/device_support/README.md \
        README.md CHANGELOG.md
git commit -m "feat: add devcode XXXX support (#NN)"
git push origin dev
```

Commit style rules for this project (see `docs/COMMIT_GUIDE.md`):

- Conventional prefix (`feat:` for a new devcode, `fix:` if it's a correction to an existing one).
- Reference the issue or PR number in parentheses at the end of the subject.
- Do NOT add AI attribution trailers.
- Contributor credit lives in the CHANGELOG entry, not the commit body.

## 9. Reference: canonical `SENSOR_TYPES`

When deciding what to map a title to, check `custom_components/dessmonitor/const.py` for the canonical key. A non-exhaustive list of keys most devcodes target:

```
Output Active Power, Output Apparent Power, Output Voltage, Output Current,
Output Frequency, Output frequency, Battery Voltage, Battery Current,
Battery Power, Battery Charging Current, Battery Discharge Current,
State of Charge, SOC, Grid Voltage, Grid Frequency, Grid Power,
PV Voltage, PV Current, PV Power, PV1 Voltage / Current / Charger Power,
PV2 Voltage / Current / Charger Power, PV Temperature, PV Radiator Temperature,
INV Module Termperature, DC Module Termperature, AC radiator temperature,
DC radiator temperature, Inverter Heat Sink Temperature,
Load Percent, Operating mode, Output priority, Charger Source Priority,
Energy Today, Energy Total, Energy Month, Energy Year,
Second Output Frequency, Second Output Voltage
```

Note the two typo-preserved temperature keys (`Termperature`): sibling devcodes typically map raw API titles to the corrected form (`"DC Module Temperature"`) because the resolver falls back to the friendly `name` field. Either form works; follow the sibling you copied from.

## 10. Checklist

Before opening a PR:

- [ ] `devcode_XXXX.py` created and registered
- [ ] Only observed or documented values in mappings; no cross-devcode leakage
- [ ] Operating mode targets are in `OPERATING_MODES` or explicitly added via the mapping
- [ ] `SENSOR_TITLE_MAPPINGS` only contains titles that fail the built-in normaliser
- [ ] `PARAMETER_SENSOR_NAMES` set iff the reporter needs a sensor from the parameters endpoint
- [ ] Root `README.md`, `device_support/README.md`, `CHANGELOG.md` all updated
- [ ] `black` / `isort` / `flake8` / `mypy` clean
- [ ] Commit subject follows `feat: add devcode XXXX support (#NN)` style
- [ ] No AI attribution in the commit or PR body
