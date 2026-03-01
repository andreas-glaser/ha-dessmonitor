# DessMonitor Device Support

This directory contains collector-specific mappings and configurations for different DessMonitor data collector models (devcodes).

**Note**: The devcode refers to the data collector/gateway device, not the inverter itself. The data collector communicates with one or more inverters and reports their data to the DessMonitor API.

## Currently Supported Collectors

- **devcode 2334**: Known to pair with EASUN 6.2KW Hybrid Solar Inverter
- **devcode 2361**: Known to pair with SRNE SR-EOV24-3.5K-5KWh
- **devcode 2376**: Known to pair with POW-HVM6.2K-48V-LIP
- **devcode 2449**: Known to pair with EASUN 8/11KWA, WKS Evo MAX II 10kVA 48V
- **devcode 2451**: Known to pair with Axpert MKS IV 5600VA
- **devcode 6422**: Known to pair with Must PH19-6048 EXP
- **devcode 6515**: Known to pair with ANENJI ANJ-HHS-11KW-48V-WIFI
- **devcode 6544**: Known to pair with ANENJI ANJ-HHS-11KW-48V

### Device Metadata

Each `devcode_XXXX.py` exposes a `DEVICE_INFO` block that describes the collector. When known, populate the optional `known_inverters` list with inverter model names (e.g., `["POW-HVM6.2K-48V-LIP"]`) so contributors quickly see which hardware has been validated for that devcode.

## Adding Support for a New Devcode

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

## Example: Adding devcode 2341

1. Copy `devcode_template.py` to `devcode_2341.py`
2. Update device info:
   ```python
   DEVICE_INFO = {
       "name": "Legacy DessMonitor Data Collector (2341)",
       "description": "Older model DessMonitor data collector/gateway",
       # ...
   }
   ```
3. Add actual mappings from your device's API responses
4. Register in `device_registry.py`:
   ```python
   from .devcode_2341 import DEVCODE_CONFIG as config_2341  
   _register_devcode(2341, config_2341)
   ```
