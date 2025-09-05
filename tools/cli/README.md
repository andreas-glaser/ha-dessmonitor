# DessMonitor CLI Tool

A Python CLI tool for DessMonitor API development and device analysis. This tool helps contributors query DessMonitor API endpoints to create device support configurations for the Home Assistant integration.

## Purpose

This tool is designed for:
- **Integration Contributors**: Developing device support for new DessMonitor hardware
- **Device Analysis**: Understanding sensor capabilities and data structures
- **API Exploration**: Testing DessMonitor API endpoints and responses
- **DevCode Discovery**: Finding device codes needed for Home Assistant integration mapping

## Installation

### Prerequisites
- Python 3.7+
- `aiohttp` library

### Setup
```bash
# Navigate to CLI directory
cd tools/cli

# Install dependencies
pip install -r requirements.txt

# Authenticate with DessMonitor API
python3 dessmonitor_cli.py auth --username YOUR_USERNAME --password YOUR_PASSWORD --company-key YOUR_COMPANY_KEY
```

## Commands

### `auth` - Authentication
Store your DessMonitor API credentials for subsequent commands.

```bash
python3 dessmonitor_cli.py auth --username USER --password PASS --company-key KEY
```

**Example:**
```bash
python3 dessmonitor_cli.py auth --username your_email@example.com --password your_password --company-key your_company_key
```

### `collectors` - List Data Collectors
Discover all available collectors (inverters/data loggers) in your account.

```bash
python3 dessmonitor_cli.py collectors
```

**Example Output:**
```
=== Data Collectors ===
PN: Q0045xxxxxxxxx | Alias: Inverter 1 | Project: MyProject | Status: Online
PN: Q0045yyyyyyyyy | Alias: Inverter 2 | Project: MyProject | Status: Offline
PN: Q0045zzzzzzzzz | Alias: Inverter 3 | Project: MyProject | Status: Online
```

**Use Case:** Find collector PNs needed for device queries.

### `devices` - List Devices
Show all devices under a specific collector.

```bash
python3 dessmonitor_cli.py devices --pn COLLECTOR_PN
```

**Example:**
```bash
python3 dessmonitor_cli.py devices --pn Q0045xxxxxxxxx
```

**Example Output:**
```
=== Devices for Collector Q0045xxxxxxxxx ===
SN: Q0045xxxxxxxxxYYYYYYY | DevCode: 2376 | DevAddr: 1 | Alias: Inverter 1
```

**Use Case:** 
- Find device serial numbers for data queries
- **Critical:** Extract DevCode (e.g., 2376) needed for Home Assistant device support

### `data` - Get Device Data
Retrieve real-time sensor readings from a device.

```bash
python3 dessmonitor_cli.py data --device-sn DEVICE_SN [--days DAYS]
```

**Example:**
```bash
python3 dessmonitor_cli.py data --device-sn Q0045xxxxxxxxxYYYYYYY --days 1
```

**Use Case:**
- See real-time sensor values
- Understand sensor naming conventions
- Test sensor data availability

### `sp-keys` - Query SP Key Parameters
Fetch the list of SP key parameter identifiers available for a device.

```bash
python3 dessmonitor_cli.py sp-keys --device-sn DEVICE_SN [--raw]
```

**Example:**
```bash
python3 dessmonitor_cli.py sp-keys --device-sn Q0045xxxxxxxxxYYYYYYY
```

**Example Output:**
```
=== SP Key Parameters for Q0045xxxxxxxxxYYYYYYY ===
- PV_OUTPUT_POWER
- LOAD_ACTIVE_POWER
- GRID_ACTIVE_POWER
- BT_BATTERY_CAPACITY
- BATTERY_ACTIVE_POWER
```

**Notes:**
- Use `--raw` to print the full JSON response from the API (usually under `dat.keys`).
- The command auto-discovers `pn`, `devcode`, and `devaddr` when possible to maximize compatibility.

### `analyze` - Device Analysis
Generate structured analysis of device capabilities for devcode development.

```bash
python3 dessmonitor_cli.py analyze --device-sn DEVICE_SN [--output OUTPUT_FILE]
```

**Example:**
```bash
python3 dessmonitor_cli.py analyze --device-sn Q0045xxxxxxxxxYYYYYYY --output analysis.json
```

**Use Case:**
- **Primary Tool** for creating device support configurations
- Generate comprehensive sensor inventories
- Extract operating modes and priority values
- Save structured analysis for documentation

## Workflow for Contributors

### 1. Device Discovery
```bash
# Find your collectors
python3 dessmonitor_cli.py collectors

# Find devices under each collector
python3 dessmonitor_cli.py devices --pn YOUR_COLLECTOR_PN
```

### 2. Device Analysis
```bash
# Analyze device capabilities
python3 dessmonitor_cli.py analyze --device-sn YOUR_DEVICE_SN --output device_analysis.json

# Get real-time data to understand sensor behavior
python3 dessmonitor_cli.py data --device-sn YOUR_DEVICE_SN
```

### 3. Create Device Support
Use the analysis output to create device support configurations in:
- `custom_components/dessmonitor/device_support/` (device-specific configurations per devcode)

Notes:
- Add a new `devcode_XXXX.py` based on the template and register it in `device_support/device_registry.py`.
## Configuration

### Authentication Storage
Credentials are stored in `.dessmonitor_cli_config.json` (ignored by git):
```json
{
  "username": "your_email@example.com",
  "password": "your_password",
  "company_key": "your_company_key",
  "token": "...",
  "secret": "...",
  "token_expires": 1234567890
}
```

### Token Management
- Tokens automatically refresh when expired
- 7-day token lifetime
- Re-authentication happens transparently

## Error Handling

### Common Errors
- **"No saved credentials"**: Run `auth` command first
- **"Device not found"**: Check device serial number and collector association
- **"API Error: ERR_FORMAT_ERROR"**: Invalid collector PN or API parameters
- **Authentication failures**: Check username, password, and company key

### Debug Mode
Enable debug logging by modifying the script:
```python
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
```
