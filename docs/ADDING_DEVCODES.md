# Adding a New Devcode

This guide explains how to request or add device support for DessMonitor or ShineMonitor, including sensor mappings and supported inverter settings.

## Request support

If Home Assistant logs `Unsupported devcode NNNN`, the integration has no
device-specific mappings for that code. It continues using raw sensor titles and
values, but some sensors may be missing or need name, unit, or operating-mode
mappings. The warning is logged once per devcode until Home Assistant restarts.

You do not need to install anything to request support, and you do not need to
type your password anywhere.

1. [Search existing issues](https://github.com/andreas-glaser/ha-dessmonitor/issues)
   for your devcode.
2. In Home Assistant, open **Settings > Devices & services > DessMonitor**, use
   the three-dot menu on the integration entry itself, and choose **Download
   diagnostics**.
3. Open a [device support request](https://github.com/andreas-glaser/ha-dessmonitor/issues/new?template=device_support.yml)
   and attach that file, or attach it to the matching existing issue.

That download covers every inverter on the account in one file. For each one it
records the devcode, whether it is `supported`, `partial` or `unsupported`, how
many of its readings reach an entity, and the title and unit of every reading
that reaches none, which is the list a maintainer works from. It also carries
the control fields, so settings can be mapped from the same file.

Home Assistant offers the same button on each inverter's own device page, and
that file carries the same report for that one device. Either is enough: attach
whichever you took. The entry download is still the better first file on a
multi-inverter account, because it covers all of them at once.

**It contains no credentials and no identifiers.** The username, password,
company key and token are redacted, and serial numbers, collector aliases and
collector product numbers appear only as a `sha256:` correlation hash, so two
downloads of the same account can still be compared without disclosing either.
Review it before attaching it, as you should with any diagnostics file.

If Home Assistant shows a **Repairs** card saying a devcode has no mappings or
is missing readings, that card is raised by this check and links here.

### If the integration will not set up at all

Then there is no diagnostics download to take, and the CLI below is the way to
produce the same evidence from a computer. It is also what to use when a cloud
write needs testing, which the integration cannot do for you.

```bash
cd tools/cli
pip install -r requirements.txt
python3 dessmonitor_cli.py report --username YOUR_USERNAME
```

Add `--api-profile shinemonitor_solar` if your account is on ShineMonitor; omit
it for DessMonitor, the default. Use the same username as your Home Assistant
integration, and a company key only if your installer gave you one
(`--company-key`). The command prompts for your password rather than taking it
on the command line, where your shell would record it.

It lists the collectors on the account, analyses every inverter behind them,
writes one redacted `analysis_<devcode>.json` per device, and prints what each
one covers, for example:

```
   Wrote analysis_6515.json (devcode 6515)
   Coverage: 34 of 79 titles reach Home Assistant as sensors (already supported)
   Every reading this collector labels with a unit already reaches Home Assistant.
```

Attach the JSON files, and paste the summary block the command prints at the
end. Share only those files, never your password or the CLI credentials file
(`.dessmonitor_cli_config.json`). The report is redacted before it is written:
`device_sn`, `collector_alias` and known identifying values in telemetry,
parameters and unit-pattern samples are blanked, including `devise serial
number` and record IDs, and the checksum is computed after redaction.
Review the file for anything else identifying; if you redact more,
mention that in the issue so the maintainer can account for checksum changes.

Either file lets a maintainer check the mappings and prepare a dev build for you
to test. To contribute the mappings yourself, continue with the workflow below.

## Background

- The **devcode** identifies the *data collector / gateway* (the WiFi/4G dongle that talks to the monitoring platform), not the inverter itself. The same inverter family can ship with different collectors, and the same collector can be rebranded across several inverter brands.
- Each supported devcode has a file `custom_components/dessmonitor/device_support/devcode_XXXX.py` that tells the integration how to translate that collector's API output into canonical sensor names, operating modes, and priority labels.
- The registry in `device_support/device_registry.py` imports the supported devcode modules. Sensors call `apply_devcode_transformations()` when reading values.
- Unknown devcodes still work through a generic fallback (raw titles and values, no enum mapping), so the goal of adding a devcode is to clean up names, normalise enum values, and expose sensors that the API hides behind verbose or typo-laden titles.

## Prerequisites

- An `analysis.json` file the reporter produced with the CLI tool using their own DessMonitor or ShineMonitor account. Contributors do not need the reporter's credentials.
- Python 3.11+ with the CLI dependencies installed as shown below.
- A local checkout of the `dev` branch.

## Workflow Overview

```
1. Reporter produces analysis.json with the CLI
2. Verify analysis.json integrity (checksum)
3. Read the analysis and pick mappings
4. Write devcode_XXXX.py following the sibling pattern
5. Register in device_registry.py
6. Check sensor coverage against the analysis and close the remaining gaps
7. Commit the redacted analysis under docs/evidence/devcodes/  (required)
8. Update README.md, device_support/README.md, CHANGELOG.md
9. Run lint/type/format checks
10. Commit and push; open a PR that references the issue and credits the reporter
```

Step 7 is not optional and is enforced by a test. A registered devcode with no
committed evidence is a profile nothing can defend: the coverage guard in
`tests/test_analysis_coverage.py` only reads devcodes it has a file for, so a
later change that stops one of its readings resolving breaks an installation
silently. That is how devcode 6514 shipped resolving its state of charge and
nothing else, dropping 58 of its 76 titles until two reporters noticed eight
months apart (#35, then #56).

`test_every_registered_devcode_is_guarded_by_committed_evidence` fails on a new
devcode with no evidence file. It carries a list of the ten devcodes registered
before this was a requirement, and that list only shrinks: a second test fails
if an entry on it has since gained evidence. If you own one of those devices, a
diagnostics download is all it takes to clear an entry.

## 1. Produce the analysis (contributor side)

One command covers the whole account. Download the
[dev branch ZIP](https://github.com/andreas-glaser/ha-dessmonitor/archive/refs/heads/dev.zip),
extract it, and open a terminal in the extracted repository folder:

```bash
cd tools/cli
pip install -r requirements.txt
python3 dessmonitor_cli.py report --username YOUR_USERNAME
```

It authenticates, enumerates collectors and devices, writes one redacted
`analysis_<devcode>.json` per device into the current directory, prints each
one's sensor coverage, and ends with a summary to paste into the issue. A
device that fails to answer is reported and the others still get written.
Add `--api-profile shinemonitor_solar` for a ShineMonitor account and
`--output-dir` to write somewhere other than the current directory.

The step-by-step equivalent is still there when you need a single device, a
non-redacted report for your own debugging, or the generated template:

```bash
python3 dessmonitor_cli.py auth \
    --username YOUR_USERNAME --company-key YOUR_COMPANY_KEY

python3 dessmonitor_cli.py collectors
python3 dessmonitor_cli.py devices --pn COLLECTOR_PN
python3 dessmonitor_cli.py analyze --redacted \
    --device-sn DEVICE_SN --output analysis_XXXX.json
```

Use the same username and company key as your Home Assistant integration. The
`auth` command prompts for your password. Replace `COLLECTOR_PN` with the PN from
`collectors`, then use the serial number for the matching devcode from `devices`
as `DEVICE_SN`. Replace `XXXX` in the output filename with your devcode. For
ShineMonitor, add `--api-profile shinemonitor_solar` to `auth`; the CLI
remembers the chosen profile for subsequent commands.

Either way the analysis is a structured JSON file containing sensor titles,
observed operating mode and priority values, unit patterns, a sample of live
data, device control fields, and an HMAC checksum.

## 2. Verify the analysis file

Integrity check, so you know the JSON has not been edited after generation:

```bash
python3 tools/cli/dessmonitor_cli.py verify /path/to/analysis_XXXX.json
```

Expected output: `Checksum OK - analysis data is intact.` (A v1 analysis without a checksum is acceptable but older; prefer v3, which includes `hint` and `unit` on value-type control fields. v2 is also valid but lacks those.)

New exports exclude `device_sn` and `collector_alias` from the checksum so reporters
can redact or remove either field without breaking validation. `--redacted` also
blanks known identifying sample/parameter values and clears their unit-pattern
samples before computing the checksum. Ordinary readings, control metadata, and
hashed correlation identifiers remain available for analysis. Nested values
remain covered by the checksum, so manually editing them changes it.
Older exports still verify with the original alias present;
if it was already redacted, regenerate the
report with the updated CLI. Updating the verifier cannot recover an alias that was
included in an older checksum.

## 3. Read the analysis

Open the analysis and note these top-level fields:

| Field | What to do with it |
|-------|--------------------|
| `devcode` | The number you will use for the filename (`devcode_XXXX.py`) and registry entry |
| `collector_alias` | Blank in redacted reports; ask the reporter for the inverter brand/model separately |
| `operating_modes` | All mode strings the collector has emitted; map any that do not match the canonical `OPERATING_MODES` list |
| `output_priorities` | Values seen from "Current output priority" / "Output priority" sensors |
| `charger_priorities` | Values seen from "Current charging priority" / "Charger Source Priority" sensors |
| `sensor_titles` | Raw API titles; compare against `SENSOR_TYPES` in `const.py` |
| `potential_typos` | Titles the CLI flagged as likely typos |
| `unit_patterns` | Shows which titles returned non-numeric strings (icon-state sensors, etc.) |
| `control_fields` | List of controllable fields. Each entry has `name`, `type` (`options` or `value`), and `id`. Options-type entries include the priority/config code enum, e.g. `{"1":"SUB","2":"SBU","3":"SUF","4":"ZEC"}`. Value-type entries include `hint` (API min/max range like `"48.0~56.0V"` or `"0-900min"`) and `unit`, which the integration parses into number-entity ranges. |
| `parameter_count` / `parameters` | Sensors only returned by `queryDeviceParsEs`, not by `queryDeviceLastData` |

The top-level `api_profile` identifies the cloud backend used for the report;
older reports may omit it.

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

The shared resolver in `sensor_titles.py`, used by both the cloud and local
paths, already tries each candidate title in turn:

1. Exact match against `SENSOR_TYPES` keys
2. Normalised match against `SENSOR_TYPES` keys
3. Normalised match against each entry's friendly `name`

Normalising trims the title, collapses internal runs of whitespace, and ignores
case, so `"Grid  Power"` and `"grid power"` both reach `"Grid Power"` without a
mapping. Only add a mapping when a raw API title would fail all three. Common
cases:

- **Verbose names**: `"Daily PV energy generation"` → `"Energy Today"`
- **Vendor typos**: `"DCDC  module Termperature"` → `"DC Module Temperature"`, `"Total Output Aparent Power"` → `"Output Apparent Power"`
- **Different wording for the same reading**: `"Total Output Active Power"` → `"Output Active Power"`
- **Exposing hidden sensors**: `"Battery SOC"` → `"State of Charge"`, `"Battery Capacity"` → `"State of Charge"`
- **Duplicate-title dedup for the summary endpoint**: map alternate names (`"energyToday"`, `"Today generation"`) to the same canonical key so the coordinator's dedup logic skips them.

A title that already resolves automatically (e.g. `"PV temperature"` →
`"PV Temperature"` via the friendly name) does NOT need a mapping. Keep the dict
minimal, and let `tools/analysis_coverage.py` tell you which titles still fail.

If a reading has no canonical key at all, add one to `SENSOR_TYPES` in
`const.py` rather than mapping it onto an unrelated sensor. Split-phase
collectors, for example, report `Output L1 Active Power` and
`Output L2 Active Power` next to the summed `Total Output Active Power`; mapping
both legs onto one key would silently drop the second.

### 4.5 `CONTROL_FIELD_MAPPINGS`

Control field names come from the `control_fields` section of the analysis and
are used verbatim as the entity name. Add a mapping only where the collector
reports a setting under an internal identifier, as devcode 6515 does with
`bat_eq_time`, or where the name is misspelled. Leading, trailing and doubled
whitespace is trimmed for every devcode, so a name such as `" Inverter Time"`
needs no mapping.

```python
CONTROL_FIELD_MAPPINGS: dict[str, str] = {
    "bat_eq_time": "Eq charging time",
}
```

A control entity's unique id is derived from its display name, so a mapping
changes that identity. `async_migrate_control_unique_ids` carries the existing
registry entry over, which keeps automations working, but it runs once: choose
the final name rather than renaming across releases.

### 4.6 `TEMPORAL_CONTROLS`

Some collectors advertise settings whose value is a clock: the secondary
charging and output priority boundaries read as `16:32`, and the inverter's own
date reads as a calendar string. A number entity cannot carry either. With no
range hint from the API, Home Assistant publishes such a control with its
default 0-100 range, and a write sends `50` into a schedule field, which the
API accepts without an error. A control of that shape that no profile declares
is therefore not published at all, on any devcode.

List the field id from the `control_fields` section of the analysis against the
platform it belongs on:

```python
TEMPORAL_CONTROLS: dict[str, str] = {
    "bat_eybond_read_61": "time",    # HH:MM, minute resolution
    "sys_eybond_read_95": "text",    # YYYY-MM-DD HH:MM:SS, no timezone
}
```

Two rules, both from #48 and #57:

- Declare a `time` field only when the committed analysis shows it reading as
  `HH:MM`. The id alone is not enough: the same id means something else on
  another devcode, which is why each profile declares its own.
- Declare a `text` clock only when a write to it has been confirmed on
  hardware for that devcode, or when its read format is at least observed. A
  calendar string in the wrong format sets the inverter clock rather than being
  rejected, and the schedules depend on that clock. Devcode 6515 advertises
  such a field, `sys_eybond_read_95`, and it stayed out of this list until a
  reported read showed the same 19-character `YYYY-MM-DD HH:MM:SS` string as
  6544's `sys_eybond_read_44023`.

Moving a field from `number` to `time` or `text` changes its entity id, so it
ships in a minor release with an upgrade note. The old number entity is
disabled once and kept, never deleted.

### 4.7 `VALUE_TRANSFORMATIONS`

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

### 4.8 `PARAMETER_SENSOR_NAMES`

Most sensors arrive via `queryDeviceLastData`. A minority (notably SOC on devcode 2376) only appear under `queryDeviceParsEs`. The analysis lists these in the `parameters` section.

If a needed sensor is *missing* from `sensor_titles` but present in `parameters`, add its raw parameter `name` here:

```python
PARAMETER_SENSOR_NAMES: set[str] = {"Battery percentage"}
```

The coordinator will fetch `queryDeviceParsEs` in parallel and merge the parameters into the device data (deduplicated). Leave empty otherwise.

### 4.9 `SETTING_READINGS`

Some collectors return the inverter's own setpoints in the telemetry call.
Devcode 2452 reports the battery recharge, bulk and float voltages, the
back-to-discharge voltage and the second output's schedule beside the live
readings, and five of those are the values of controls the same account
publishes as number and select entities. They carry a unit, so the support
report counted them among the readings that reach no entity and the Repairs
card told the owner that fourteen readings were missing while none were (#53).

List such titles here, exactly as the collector spells them. They then count as
neither resolved nor dropped, the coverage tool marks them `(setting)`, and the
committed-evidence guard stops demanding a sensor for them:

```python
SETTING_READINGS: set[str] = {
    "Battery bulk voltage",
    "Battery float voltage",
}
```

Two rules:

- A setting is not a sensor. Mapping one onto a `SENSOR_TYPES` key publishes a
  second entity for a value the number or select entity already owns.
- Declare only what the committed evidence shows, and only where the reading
  really is a setting. A nameplate rating is not: it is a read-only fact about
  the hardware, so it becomes a diagnostic sensor, as `rated power` and
  `battery rated voltage` do on this devcode.
- Spell each entry as the *reading* is titled, not as the control template
  names it. A collector does not always spell the two the same: devcode 2477
  reports "Beeps While Primary Source Interupt" and "Transfer To Bypass @
  Overload" as readings against a "...Interrupt" and a "Transfer To Bypass
  Overload" control (#61).
- A title that also arrives as a live reading is not declared. Devcode 2477
  sends `Output Voltage` and `Output Frequency` twice, once measured and once
  as the setpoint; declaring either would take away the sensor.

### 4.10 `ABSENT_READINGS`

A collector reports every field its protocol defines, whether the hardware
behind it fills that field or not, and the empty ones carry units too. Devcode
4743 reports the S and T phase voltages, currents, powers and frequencies on a
single-phase inverter, and three string powers on a unit with one string
connected, all at zero. They looked exactly like dropped readings, so the
support report counted sixteen of them and the Repairs card told an owner whose
sensors all worked that sixteen readings were missing (#58).

List such titles here with the reason the hardware leaves them empty, spelled
as the collector titles them. They then count as neither resolved nor dropped,
the coverage tool marks them `(declared absent on this hardware)`, and the
committed-evidence guard stops demanding a sensor for them:

```python
_IDLE_PHASE = "single-phase hardware leaves the S and T phases unfilled"

ABSENT_READINGS: dict[str, str] = {
    "Inverter S phase voltage": _IDLE_PHASE,
    "Inverter T phase voltage": _IDLE_PHASE,
}
```

Two rules:

- Declare absence, not ignorance. A reading you have not worked out yet is a
  reading to map, and declaring it here hides it from the guard that exists to
  find it. The reason string is read by a human reviewing the profile, so write
  what the evidence shows rather than a restatement of the title.
- A field one owner's hardware leaves empty may be filled on another's. Zero on
  a three-phase title is evidence about *that* reporter's inverter, so declare
  it only where the devcode's hardware cannot fill it, and map it the moment a
  report shows a value. The resolver is unaffected either way: a declared title
  that does start arriving with a value still needs a mapping to reach a sensor.

### 4.11 Configuration

```python
DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "control_field_mappings": CONTROL_FIELD_MAPPINGS,
    "temporal_controls": TEMPORAL_CONTROLS,
    "value_transformations": VALUE_TRANSFORMATIONS,
    "parameter_sensor_names": PARAMETER_SENSOR_NAMES,
    "setting_readings": SETTING_READINGS,
    "absent_readings": ABSENT_READINGS,
}
```

For hardware variants that share API option lists, an optional
`control_options_filter` callback can be added to `DEVCODE_CONFIG`. Follow
[`devcode_2477.py`](../custom_components/dessmonitor/device_support/devcode_2477.py):
the callback accepts a parameter ID, the API option mapping, and device data. It
returns a subset of the original options without changing their keys, or raises
`ValueError` when the metadata cannot establish valid options. The select entity
logs the reason, becomes unavailable, and retries on coordinator updates and before
writes. Use reported ratings; a live voltage or current setting does not establish
hardware limits.

## 5. Register the devcode

Append to `device_support/device_registry.py` inside `_load_device_configurations()`:

```python
from .devcode_XXXX import DEVCODE_CONFIG as config_XXXX

_register_devcode(XXXX, config_XXXX)
```

Match the surrounding style (blank line between each import/register pair).

## 6. Check sensor coverage

A devcode added for one reported symptom tends to leave the rest of the
collector's telemetry unmapped, because nothing in review shows which titles the
resolver still rejects. That is how devcode 6514 shipped with SOC support while
grid power, output power and both output legs stayed invisible (#35, then #56).

Run the coverage report against the analysis:

```bash
.venv/bin/python tools/analysis_coverage.py path/to/analysis_XXXX.json
```

The `report` command prints a summary of the same thing on the reporter's own
machine, so an issue may already name the readings that resolve to nothing. This
is the detailed form of it, and it is the one to work from.

Both shapes of evidence are accepted: a CLI `analysis_<devcode>.json` and a
diagnostics download. The tool prints which produced the file, and a download
records a unit for *every* reading where a CLI analysis records one for the
sampled readings only, so a committed download guards more of a devcode than a
committed analysis does. A download is read exactly as the reporter attached
it: Home Assistant wraps the report under a `data` key, and the tool unwraps
that envelope itself (#62).

It prints every raw title with the canonical key it resolves to, then the
unresolved ones, marking those the collector labelled with a unit, those a
profile declares a setting, and those the same report lists in the device's
control template - a title marked `(control on this device)` is a setting to
declare rather than a reading being dropped.

Where the report carries the control readbacks, which a diagnostics download
does and a CLI analysis does not, an unresolved title is also printed with any
control sitting at the same value:

```
    Battery Re-Charge Voltage  [V]
        reads 44, as the control 'Back to Grid Voltage' does - a setting to
        declare if the two are one
```

That is the pairing the names cannot make, because a collector does not spell a
reading and its control alike. It is a candidate and not a declaration: two
settings of one inverter can sit at the same value, and a live reading can pass
through a setpoint's, so confirm it against the control's own name and option
list before declaring it. Pass `--controls` to also list the control fields
whose names no reading title matches. A unit means the title is a reading and should
become a sensor, unless it is a setting; unresolved titles without one
are settings, identity fields and timestamps, which reach Home Assistant through
the number, select and button platforms instead. Work through the marked titles
until none remain, then re-run the report.

## 7. Commit the analysis as evidence

Save the reporter's redacted analysis to `docs/evidence/devcodes/analysis_XXXX.json`
so the next report against the same devcode can be answered without asking for
the data again. `tests/test_analysis_coverage.py` reads every analysis committed
under `docs/evidence/` and fails when a reading that carries a unit no longer
resolves, which keeps a later `const.py` or mapping edit from silently dropping
one.

A diagnostics download is committed under the same `analysis_XXXX.json` name,
because that is what the test globs for. One command does it:

```bash
.venv/bin/python tools/evidence_from_diagnostics.py ~/Downloads/config_entry-dessmonitor-01ABC.json
```

It keeps the integration's own sections verbatim, because their checksums cover
them, drops the host and config-entry sections that say nothing about the
devcode, verifies every device checksum, refuses to write if one fails, and
writes one file per devcode the download covers. Add `--dry-run` to look first
and `--force` to replace existing evidence.

To see what an issue's attachments say before any of that:

```bash
.venv/bin/python tools/triage.py 62
```

It reads the issue and its comments, downloads each attached report into a
temporary directory, and prints each devcode's coverage, the readings that
carry a unit and reach no entity, and any reading whose local and cloud
figures disagree about scale.

Only commit a CLI report produced with `--redacted`, and confirm `device_sn` and
`collector_alias` are empty before adding it. If the reporter supplied an
unredacted file, redact it first:

```bash
.venv/bin/python - <<'EOF'
import json, sys
sys.path.insert(0, "tools/cli")
from evidence import redact_analysis

with open("analysis_XXXX.json") as handle:
    report = json.load(handle)
report["analysis"] = redact_analysis(report["analysis"])
with open("docs/evidence/devcodes/analysis_XXXX.json", "w") as handle:
    json.dump(report, handle, indent=2)
    handle.write("\n")
EOF

.venv/bin/python tools/cli/dessmonitor_cli.py verify docs/evidence/devcodes/analysis_XXXX.json
```

Redaction recomputes the checksum, so the committed file still verifies.

## 8. Update documentation and changelog

Three files to edit:

1. `README.md` — add the inverter to the `**Known models:**` list under
   `## Supported Inverters`, keeping it alphabetical.
2. `custom_components/dessmonitor/device_support/README.md` — add a bullet under `## Currently Supported Collectors`:
   ```markdown
   - **devcode XXXX**: Known to pair with Brand Model X
   ```
3. `CHANGELOG.md` — add an entry under `## [Unreleased]` → `### Added`:
   ```markdown
   - Support for devcode XXXX (Brand Model X) with <one-line summary of mappings> (#NN, thanks to @contributor for the CLI analysis data).
   ```
   Create the `### Added` section if `[Unreleased]` does not already have one.

## 9. Quality checks

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

## 10. Commit and push

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

## 11. Reference: canonical `SENSOR_TYPES`

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
Second Output Frequency, Second Output Voltage,
Output L1 / L2 Active Power, Output L1 / L2 Apparent Power,
Output L1 / L2 Voltage, Output L1 / L2 Current,
Load L1 / L2 Percentage
```

Note the two typo-preserved temperature keys (`Termperature`): sibling devcodes typically map raw API titles to the corrected form (`"DC Module Temperature"`) because the resolver falls back to the friendly `name` field. Either form works; follow the sibling you copied from.

## 12. Checklist

Before opening a PR:

- [ ] `devcode_XXXX.py` created and registered
- [ ] Only observed or documented values in mappings; no cross-devcode leakage
- [ ] Operating mode targets are in `OPERATING_MODES` or explicitly added via the mapping
- [ ] `SENSOR_TITLE_MAPPINGS` only contains titles that fail the shared resolver
- [ ] `PARAMETER_SENSOR_NAMES` set iff the reporter needs a sensor from the parameters endpoint
- [ ] `SETTING_READINGS` lists every setpoint the collector returns among the readings, and no nameplate rating
- [ ] `ABSENT_READINGS` lists only titles this hardware cannot fill, each with the reason, and no title awaiting a mapping
- [ ] `TEMPORAL_CONTROLS` lists every advertised clock-valued field whose read format the analysis shows, and nothing else
- [ ] `tools/analysis_coverage.py` reports no unresolved title carrying a unit
- [ ] Redacted analysis committed under `docs/evidence/devcodes/` and `verify` passes
- [ ] Root `README.md`, `device_support/README.md`, `CHANGELOG.md` all updated
- [ ] `black` / `isort` / `flake8` / `mypy` clean
- [ ] Commit subject follows `feat: add devcode XXXX support (#NN)` style
- [ ] No AI attribution in the commit or PR body
