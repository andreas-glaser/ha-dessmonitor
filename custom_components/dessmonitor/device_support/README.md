# DessMonitor Device Support

This directory contains device profiles for inverters connected through DessMonitor or ShineMonitor. Profiles map sensor readings and supported configuration fields to Home Assistant entities. Available settings, options, and ranges come from the device's cloud API metadata.

**Note**: The devcode refers to the data collector/gateway device, not the inverter itself. The data collector communicates with one or more inverters and reports their data to the selected platform. A cloud profile does not establish local protocol support or make settings writable locally.

## Currently Supported Collectors

- **devcode 518**: Known to pair with BYD BYD-S-1P5K-2M through Q0025-series collectors on ShineMonitor; local protocol and writes are not verified.
- **devcode 632**: Grid-connected PV inverter with up to three strings and an optional export meter, on ShineMonitor; inverter brand and model not yet confirmed. No battery, charger or priority readings. `DCI`, `GFCI` and `ISO` stay unmapped because the analysis records no unit for them.
- **devcode 684**: Known to pair with the Panther Solar PES-3000TL-SS, a 3 kW single-phase grid-connected PV inverter on ShineMonitor; its nameplate ratings match what the collector reports. No battery, charger or priority readings, and the platform reports no control template for it, so it publishes sensors only. The seven `fault information` words stay unmapped: they are raw bitmasks and no report carries the vendor fault table for this protocol.
- **devcode 4743**: Single-phase grid-connected PV inverter with up to three strings, on ShineMonitor; inverter brand and model not yet confirmed. No battery readings. The R phase is mapped to the grid sensors, and the S and T phases, the S and T load voltages and the unconnected string powers are declared in `ABSENT_READINGS`: the reported hardware is single-phase with one string, so the collector returns those fields at zero and they are not dropped readings. Map them when a three-phase or multi-string unit on this devcode is reported.

- **devcode 2334**: Known to pair with EASUN 6.2KW Hybrid Solar Inverter
- **devcode 2341**: Known to pair with an EASUN hybrid and a PowMr MPS-V plus 3.5 kW, both 24 V units (#72, #73). Shares the Voltronic PI30 title and control vocabulary in `eybond_voltronic.py` with devcode 2477: the same reading spellings, the same nameplate ratings as diagnostic sensors, the same `SETTING_READINGS`, and the same 24 V / 48 V battery-voltage dropdown filtering.
- **devcode 2361**: Known to pair with SRNE SR-EOV24-3.5K-5KWh
- **devcode 2376**: Known to pair with POW-HVM6.2K-48V-LIP
- **devcode 2449**: Known to pair with EASUN 8/11KWA, WKS Evo MAX II 10kVA 48V
- **devcode 2451**: Known to pair with Axpert MKS IV 5600VA
- **devcode 2428**: Known to pair with Hybrid inverter
- **devcode 2452**: Known to pair with Axpert (PI18 protocol, rebranded). Reports its nameplate ratings as diagnostic sensors and declares the setpoints it returns among the readings in `SETTING_READINGS`, five of which the account also publishes as controls.
- **devcode 2477**: Known to pair with Novopal NP35PEU24 (3500 VA, 24 V, 230 V / 50 Hz), confirmed from the nameplate in #61; also reported as a 48 V / 5 kW unit in #40, whose model is still unconfirmed. Battery-voltage dropdowns use the reported 24 V / 48 V rating. Reports its nameplate ratings as diagnostic sensors and declares the setpoints it returns among the readings in `SETTING_READINGS`; its reading titles and control-field names are not spelled the same. Shares that vocabulary with devcode 2341 through `eybond_voltronic.py`.
- **devcode 6416**: Known to pair with PowMr POW-HVM6.2M-48V-N
- **devcode 6422**: Known to pair with Must PH19-6048 EXP
- **devcode 6514**: Known to pair with ANENJI 5KW 48V Hybrid Solar Inverter, Aninerel 6.2KW 48V, Aninerel 4.2KW 24V (firmware 8.50.18.3, external Wi-Fi module), and ANENJI 4.2KW 24V. Reports each output leg (L1/L2) alongside the summed output, and declares the setpoints it returns among the readings in `SETTING_READINGS`, each the value of a control the account publishes.
- **devcode 6515**: Known to pair with ANENJI ANJ-HHS-11KW-48V-WIFI and Maxsky EM11000 11kW 48V, the latter reported with an Eybond WiFi datalogger
- **devcode 6544**: Known to pair with ANENJI ANJ-HHS-11KW-48V and ANENJI ANJ-11KW-48V-W-P. Read-only Modbus protocol-number 4 samples are verified for the latter; see the [local guide](../../../docs/LOCAL_MODE.md).
- **devcode 2507**: Known to pair with ANENJI ANJ-6200W-48PL-WIFI
- **devcode 6489**: Known to pair with a JSD Solar 5.5 kW 48 V hybrid inverter behind a `WFBLE.RTU.Bar` collector on firmware 7.6.5.11, on DessMonitor. This collector leads with a short dashboard block and then repeats the measurements in full sections, so `Output voltage` and the mains frequency each arrive twice and land on one sensor. The BMS reports its own voltage, current, temperature, SOC, capacity and charge limits beside the inverter's measurements of the same pack. Twenty setpoints it returns among the readings are declared in `SETTING_READINGS`, only one of which (`Maximum charging current`) is also a control. `BMS status`, the two BMS code words and `DCDC control status` stay unmapped: they carry no unit and no report says what their values mean. `system time` and `Power generation statistics time` are clock-shaped controls whose read format is still unobserved, so `TEMPORAL_CONTROLS` does not yet classify them.

### Device Metadata

Each `devcode_XXXX.py` exposes a `DEVICE_INFO` block that describes the collector. When known, populate the optional `known_inverters` list with inverter model names (e.g., `["POW-HVM6.2K-48V-LIP"]`) so contributors quickly see which hardware has been validated for that devcode.

## Adding Support for a New Devcode

For the full workflow (CLI analysis, mapping rules, changelog, commit style), see [`docs/ADDING_DEVCODES.md`](../../../docs/ADDING_DEVCODES.md). The short version below is a quick reference.

To add support for a new devcode, follow these steps:

### 1. Create Device Configuration File

1. Copy `devcode_template.py` to `devcode_XXXX.py` (replace XXXX with your devcode)
2. Update all mappings in the new file with values specific to your data collector

### 2. Find Your Collector's Values

To find the correct mappings for your data collector:

1. **Check Home Assistant logs** for your collector's sensor values
2. **Look at diagnostics** in Home Assistant: Settings → Devices → Your Collector → Download Diagnostics

Key sensors to check:
- `Output priority` - for output priority mappings
- `Charger Source Priority` - for charger priority mappings  
- `Operating mode` - for operating mode mappings
- Any sensor titles that have typos or could be clearer

### 3. Update the Registry

Add your new devcode to `device_registry.py`:

```python
# Add this import with the others
from .devcode_XXXX import DEVCODE_CONFIG as config_XXXX
_register_devcode(XXXX, config_XXXX)
```

### 4. Test Your Configuration

1. Restart Home Assistant
2. Check logs for any errors
3. Verify sensor names and values look correct
4. Test that mappings work as expected

### 5. Submit Your Contribution

1. Create a pull request with your new devcode file
2. Include information about your device model
3. Add test data if possible

## File Structure

```
device_support/
├── __init__.py                 # Module exports
├── device_registry.py          # Central registry and mapping functions  
├── devcode_2376.py            # Support for devcode 2376
├── devcode_template.py        # Template for new devcodes
└── README.md                  # This file
```

## Example: Adding devcode 9999

The number below is a placeholder; use your own. Check that no
`devcode_<n>.py` already exists for it first.

1. Copy `devcode_template.py` to `devcode_9999.py`
2. Update device info:
   ```python
   DEVICE_INFO = {
       "name": "Eybond Data Collector (devcode 9999)",
       "description": "Eybond data collector/gateway",
       # ...
   }
   ```
3. Add actual mappings from your device's API responses
4. Register in `device_registry.py`:
   ```python
   from .devcode_9999 import DEVCODE_CONFIG as config_9999
   _register_devcode(9999, config_9999)
   ```
