#!/usr/bin/env python3
"""
DessMonitor CLI Tool

A Python CLI tool to help contributors query DessMonitor API endpoints
for creating devcode support configurations.

Usage:
    python dessmonitor_cli.py --help
    python dessmonitor_cli.py auth --username USER --password PASS --company-key KEY
    python dessmonitor_cli.py collectors
    python dessmonitor_cli.py devices --pn COLLECTOR_PN
    python dessmonitor_cli.py data --device-sn DEVICE_SN --days 1
    python dessmonitor_cli.py analyze --device-sn DEVICE_SN
"""

import argparse
import asyncio
import getpass
import hashlib
import hmac
import json
import logging
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

# Setup logging
log_level = logging.DEBUG if "--debug" in sys.argv else logging.INFO
if "--debug" in sys.argv:
    sys.argv.remove("--debug")  # Remove it so argparse doesn't complain
logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def _write_private_file(path_value: str | Path, content: str) -> Path:
    """Write a regular mode-0600 file without following a symlink."""
    source_path = Path(path_value).expanduser()
    if source_path.is_symlink():
        raise ValueError("output path must not be a symbolic link")
    path = source_path.resolve()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("output path must be a regular file")
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)
    return path


def _write_private_json(path_value: str | Path, data: Any) -> Path:
    """Serialize one private JSON report deterministically."""
    return _write_private_file(path_value, json.dumps(data, indent=2) + "\n")


class DessMonitorCLI:
    """DessMonitor API client for CLI usage."""
    
    def __init__(self):
        self.base_url = "https://api.dessmonitor.com/public/"
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.secret: Optional[str] = None
        self.token_expires: Optional[int] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.company_key: Optional[str] = None
        self.config_file = Path(__file__).parent / ".dessmonitor_cli_config.json"
    
    async def __aenter__(self):
        # Use aiohttp's thread-based resolver so the contributor CLI does not
        # depend on the locally installed pycares/aiodns ABI combination.
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _is_token_expired(self) -> bool:
        """Check if the current token is expired."""
        if not self.token or not self.token_expires:
            return True
        return int(time.time()) >= self.token_expires
    
    def _sha1(self, data: str) -> str:
        """Generate SHA-1 hash."""
        return hashlib.sha1(data.encode()).hexdigest()
    
    def _create_signature(self, action: str, params: Dict[str, Any], salt: str) -> str:
        """Create SHA-1 signature for API request."""
        # Create action string like Home Assistant integration
        action_string = f"&action={action}"
        if params:
            for key, value in params.items():
                action_string += f"&{key}={value}"
        
        # Generate signature based on authentication state
        if self.token and self.secret:
            # Authenticated requests use token + secret
            signature_string = f"{salt}{self.secret}{self.token}{action_string}"
        else:
            # Initial auth uses password hash
            pwd_sha1 = self._sha1(self.password) if self.password else ""
            signature_string = f"{salt}{pwd_sha1}{action_string}"
        
        return self._sha1(signature_string)
    
    async def _make_request(self, action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to DessMonitor API."""
        if params is None:
            params = {}
        
        # Auto-authenticate if needed
        if action != "authSource" and self._is_token_expired():
            await self.authenticate_from_config()
        
        # Generate salt and signature
        salt = str(int(time.time() * 1000))
        signature = self._create_signature(action, params, salt)
        
        # Build URL
        url = f"{self.base_url}?sign={signature}&salt={salt}"
        if self.token and action != "authSource":
            url += f"&token={self.token}"
        url += f"&action={action}"
        
        # Add parameters
        for key, value in params.items():
            url += f"&{key}={value}"
        
        logger.debug(
            "API request action=%s parameter_keys=%s",
            action,
            sorted(params),
        )
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"API HTTP {response.status} for action {action}"
                    )

                data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            # aiohttp exception strings may contain the complete signed URL,
            # including the bearer token. Never propagate or log that text.
            raise RuntimeError(
                f"API transport failed for action {action} "
                f"({type(err).__name__})"
            ) from None

        logger.debug(
            "API response action=%s status=%s top_level_keys=%s",
            action,
            data.get("err"),
            sorted(data),
        )

        if data.get("err") != 0:
            error_code = data.get("err")
            raise RuntimeError(f"API rejected action {action} (code: {error_code})")

        return data
    
    async def authenticate(self, username: str, password: str, company_key: str) -> bool:
        """Authenticate with DessMonitor API."""
        # Store credentials for signature generation
        self.username = username
        self.password = password
        self.company_key = company_key
        
        auth_params = {
            "usr": username,
            "company-key": company_key,
            "source": "1",
            "_app_client_": "web",
            "_app_id_": "ha-dessmonitor",
            "_app_version_": "1.0.0",
        }
        
        try:
            response = await self._make_request("authSource", auth_params)
            logger.debug(
                "Authentication response status=%s keys=%s",
                response.get("err"),
                sorted(response),
            )
            
            if response.get("err") == 0 and "dat" in response:
                data = response["dat"]
                self.token = data.get("token")
                self.secret = data.get("secret")
                expire_duration = data.get("expire")
                
                if not self.token:
                    logger.error("Authentication failed: No token received")
                    return False
                
                if expire_duration:
                    self.token_expires = int(time.time()) + expire_duration
                else:
                    self.token_expires = int(time.time()) + (7 * 24 * 60 * 60)  # Default 7 days
                
                # Save credentials
                config = {
                    "username": username,
                    "password": password,
                    "company_key": company_key,
                    "token": self.token,
                    "secret": self.secret,
                    "token_expires": self.token_expires
                }
                
                self._write_private_config(config)
                
                logger.info("Authentication successful! Credentials saved.")
                logger.debug(f"Token expires in {expire_duration} seconds")
                return True
            else:
                error_code = response.get("err")
                error_desc = response.get("desc", "Unknown error")
                logger.error(f"Authentication failed: {error_desc} (code: {error_code})")
                return False
                
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    async def authenticate_from_config(self) -> bool:
        """Authenticate using saved credentials."""
        if not self.config_file.exists():
            raise Exception("No saved credentials found. Run 'auth' command first.")

        if self.config_file.is_symlink():
            raise Exception("Refusing to read credentials through a symbolic link.")
        os.chmod(self.config_file, 0o600)
        with open(self.config_file, "r") as f:
            config = json.load(f)
        
        # Load stored credentials
        self.username = config.get("username")
        self.password = config.get("password") 
        self.company_key = config.get("company_key")
        
        # Check if saved token is still valid
        if (config.get("token") and 
            config.get("secret") and 
            config.get("token_expires", 0) > time.time()):
            self.token = config["token"]
            self.secret = config["secret"]
            self.token_expires = config["token_expires"]
            logger.debug("Using valid saved token")
            return True
        
        # Re-authenticate with saved credentials
        logger.debug("Saved token expired, re-authenticating...")
        return await self.authenticate(
            self.username,
            self.password, 
            self.company_key
        )

    def _write_private_config(self, config: Dict[str, Any]) -> None:
        """Write credentials mode 0600 without following symbolic links."""
        _write_private_json(self.config_file, config)
    
    async def get_collectors(self) -> List[Dict[str, Any]]:
        """Get all collectors/data collectors."""
        collectors = []
        
        # Get projects first
        projects_response = await self._make_request("queryPlants", {"pagesize": "50"})
        
        logger.debug("Projects response received")
        projects_data = projects_response.get("dat", {})
        for project in projects_data.get("plant", []):
            pid = project.get("pid")
            if not pid:
                continue
            
            logger.info(f"Querying collectors for project: {project.get('name', pid)}")
            
            # Get collectors for this project
            page = 0  # Start from page 0 like HA integration
            pagesize = 50
            
            while True:
                try:
                    collectors_response = await self._make_request(
                        "webQueryCollectorsEs",
                        {"pid": pid, "page": page, "pagesize": pagesize}
                    )
                    
                    if "dat" in collectors_response:
                        dat = collectors_response["dat"]
                        batch_collectors = dat.get("collector", [])
                    else:
                        batch_collectors = []
                        
                    if not batch_collectors:
                        break
                except Exception as e:
                    logger.debug(f"No collectors found for project {pid}: {e}")
                    break
                
                for collector in batch_collectors:
                    collector["project_id"] = pid
                    collector["project_name"] = project.get("name", "Unknown")
                    collectors.append(collector)
                
                if len(batch_collectors) < pagesize:
                    break
                
                page += 1
        
        # Also try direct collector query (for collectors not associated with projects)
        try:
            logger.info("Querying collectors directly...")
            direct_response = await self._make_request("queryCollectorCountEs")
            logger.debug("Direct collector response received")
            
            # This endpoint might return collector count, not actual collectors
            # Let's also try the queryCollectorList endpoint
            try:
                list_response = await self._make_request("queryCollectorList")
                logger.debug("Collector list response received")
                
                if "dat" in list_response:
                    for collector in list_response.get("dat", []):
                        collector["project_id"] = None  # No project association
                        collector["project_name"] = "Direct"
                        collectors.append(collector)
                        
            except Exception as e:
                logger.debug(f"queryCollectorList failed: {e}")
                
        except Exception as e:
            logger.debug(f"Direct collector query failed: {e}")
        
        return collectors
    
    async def get_devices(self, collector_pn: str) -> Dict[str, Any]:
        """Get devices for a specific collector."""
        response = await self._make_request("queryCollectorDevices", {"pn": collector_pn})
        return response.get("dat", {})
    
    async def _find_device_info(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """Find a device across all collectors and return its details."""
        collectors = await self.get_collectors()
        
        for collector in collectors:
            pn = collector.get("pn")
            if not pn:
                continue
                
            try:
                devices_data = await self.get_devices(pn)
                devices = devices_data.get("dev", [])  # Note: key is "dev", not "devices"
                
                for device in devices:
                    if device.get("sn") == device_sn:
                        # Return device info with collector PN
                        return {
                            "pn": pn,
                            "devcode": device.get("devcode"),
                            "devaddr": device.get("devaddr"), 
                            "sn": device_sn,
                            "alias": device.get("alias"),
                            "collector_alias": collector.get("alias")
                        }
            except Exception as e:
                logger.debug(
                    "Unable to inspect one collector while locating the selected device: %s",
                    type(e).__name__,
                )
                continue
        
        return None
    
    async def get_device_data(self, device_sn: str, days: int = 1) -> List[Dict[str, Any]]:
        """Get recent data for a device."""
        # First try to find the device across all collectors to get required parameters
        device_info = await self._find_device_info(device_sn)
        
        if device_info:
            # Found device in collector, use full parameters
            params = {
                "pn": device_info["pn"], 
                "devcode": device_info["devcode"],
                "devaddr": device_info["devaddr"],
                "sn": device_sn,
                "i18n": "en"
            }
        else:
            # Try direct query with just serial number
            logger.debug("Selected device not found in collectors; trying direct query")
            params = {
                "sn": device_sn,
                "i18n": "en"
            }
        
        try:
            response = await self._make_request("queryDeviceLastData", params)
            return response.get("dat", [])
        except Exception as e:
            # If direct query fails, try with minimal params
            logger.debug(f"Direct query failed: {e}, trying alternative endpoints")

            # Try alternative endpoint for device info
            try:
                response = await self._make_request("queryDeviceInfo", {"sn": device_sn})
                device_data = response.get("dat", {})
                
                # Extract devcode from device info response
                if device_data:
                    return [{"title": "Device Info", "devcode": device_data.get("devcode"), **device_data}]
            except:
                pass
            
            # If all else fails, raise original error
            raise Exception("Unable to retrieve data for the selected device")

    async def get_device_control_fields(
        self, pn: str, devcode: int, devaddr: int, device_sn: str
    ) -> Dict[str, Any]:
        """Return control/parameter metadata (queryDeviceCtrlField)."""
        params = {
            "i18n": "en_US",
            "source": "1",
            "pn": pn,
            "devcode": devcode,
            "devaddr": devaddr,
            "sn": device_sn,
        }

        response = await self._make_request("queryDeviceCtrlField", params)
        control_data = response.get("dat", {})
        fields = control_data.get("field", [])

        formatted: Dict[str, Any] = {}
        for field in fields:
            name = field.get("name", "")
            if not name:
                continue

            entry: Dict[str, Any] = {
                "id": field.get("id"),
                "type": "value",
            }

            items = field.get("item") or []
            if items:
                entry["type"] = "options"
                options = {}
                for item in items:
                    key = item.get("key")
                    val = item.get("val")
                    if key is not None:
                        options[str(key)] = val
                entry["options"] = options
            else:
                entry["unit"] = field.get("unit")
                entry["hint"] = field.get("hint")

            formatted[name] = entry

        logger.debug(
            "Collected %d control fields for the selected device", len(formatted)
        )
        return formatted

    async def get_device_parameters(
        self, pn: str, devcode: int, devaddr: int, device_sn: str
    ) -> Dict[str, Any]:
        """Return device parameters (queryDeviceParsEs)."""
        params = {
            "i18n": "en_US",
            "source": "1",
            "pn": pn,
            "devcode": devcode,
            "devaddr": devaddr,
            "sn": device_sn,
        }

        response = await self._make_request("queryDeviceParsEs", params)
        param_data = response.get("dat", {})
        parameters = param_data.get("parameter", [])

        formatted: Dict[str, Any] = {}
        for param in parameters:
            name = param.get("name")
            if not name:
                continue

            formatted[name] = {
                "value": param.get("val"),
                "unit": param.get("unit"),
                "id": param.get("par"),
            }

        logger.debug(
            "Collected %d parameters for the selected device", len(formatted)
        )
        return formatted

    async def get_sp_key_parameters(self, device_sn: str) -> Dict[str, Any]:
        """Query SP key parameters (querySPKeyParameters) for a device.

        Tries with full parameters first (pn/devcode/devaddr/sn/i18n) and
        falls back to lighter parameter sets if required by the endpoint.
        """
        device_info = await self._find_device_info(device_sn)

        attempts: List[Dict[str, Any]] = []
        if device_info:
            attempts.append({
                "pn": device_info["pn"],
                "devcode": device_info["devcode"],
                "devaddr": device_info["devaddr"],
                "sn": device_sn,
                "i18n": "en",
            })
            attempts.append({
                "devcode": device_info["devcode"],
                "devaddr": device_info["devaddr"],
                "sn": device_sn,
                "i18n": "en",
            })

        attempts.append({"sn": device_sn, "i18n": "en"})

        last_err: Optional[Exception] = None
        for params in attempts:
            try:
                resp = await self._make_request("querySPKeyParameters", params)
                return resp
            except Exception as e:
                last_err = e
                logger.debug(f"querySPKeyParameters failed with params {params}: {e}")

        raise Exception(f"Unable to query SP key parameters for {device_sn}: {last_err}")
    
    async def set_device_control_value(self, device_sn: str, param_id: str, value: str) -> Dict[str, Any]:
        """Set a device control value (ctrlDevice)."""
        device_info = await self._find_device_info(device_sn)
        if not device_info:
            raise Exception(f"Device {device_sn} not found")

        params = {
            "pn": device_info["pn"],
            "devcode": device_info["devcode"],
            "devaddr": device_info["devaddr"],
            "sn": device_sn,
            "id": param_id,
            "val": value,
            "i18n": "en_US",
            "source": "1",
        }

        logger.info(f"Setting param {param_id} to {value} for device {device_sn}")
        return await self._make_request("ctrlDevice", params)

    def generate_devcode_template(self, analysis: Dict[str, Any]) -> str:
        """Generate a devcode template file based on analysis results."""
        try:
            devcode = int(analysis["devcode"])
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError("analysis does not contain a numeric devcode") from err
        collector_alias = str(
            analysis.get("collector_alias", "DessMonitor collector")
        )
        device_name = f"{collector_alias} (devcode {devcode})"
        local_model = str(analysis.get("local_evidence", {}).get("model", "")).strip()
        known_inverters = [local_model] if local_model else []
        
        template = f'''"""Device support for DessMonitor devcode {devcode}.

Review every suggested mapping against the attached support evidence.

This file contains all collector-specific mappings and configurations for devcode {devcode}.
The devcode represents the data collector/gateway device, not the inverter itself.

TO CONTRIBUTE:
1. Review and update all mappings below with appropriate descriptions
2. Test with your collector to ensure mappings work correctly
3. Submit a PR to the ha-dessmonitor repository
"""

from __future__ import annotations

# Device Information
# TODO: Update with accurate information about your data collector model
DEVICE_INFO = {{
    "name": {device_name!r},
    "description": "TODO: Add description of your data collector/gateway device",
    "manufacturer": "DessMonitor",  # TODO: Update if different
    "known_inverters": {known_inverters!r},
    "supported_features": [
        # TODO: Review and update based on your device capabilities
        "real_time_monitoring",
        "energy_tracking",
        "battery_management",
        "solar_tracking",
        "parameter_control",
    ],
}}

# Output Priority Mappings
# Map the API values to user-friendly descriptions
OUTPUT_PRIORITY_MAPPING = {{'''
        
        # Add output priority mappings
        if analysis.get("output_priorities"):
            template += "\n    # Found values in your device data:\n"
            for priority in analysis["output_priorities"]:
                description = f"TODO: Add description for {priority}"
                template += f"    {str(priority)!r}: {description!r},\n"
        else:
            template += '\n    # No output priority values found in device data\n'
            template += '    # Example: "SBU": "Solar → Battery → Utility",\n'
        
        template += '''}

# Charger Priority Mappings
# Map the API values to user-friendly descriptions
CHARGER_PRIORITY_MAPPING = {'''
        
        # Add charger priority mappings
        if analysis.get("charger_priorities"):
            template += "\n    # Found values in your device data:\n"
            for priority in analysis["charger_priorities"]:
                description = f"TODO: Add description for {priority}"
                template += f"    {str(priority)!r}: {description!r},\n"
        else:
            template += '\n    # No charger priority values found in device data\n'
            template += '    # Example: "PV First": "Solar charging priority",\n'
        
        template += '''}

# Operating Mode Mappings
# Map the API values to user-friendly descriptions
OPERATING_MODE_MAPPING = {'''
        
        # Add operating mode mappings
        if analysis.get("operating_modes"):
            template += "\n    # Found values in your device data:\n"
            for mode in analysis["operating_modes"]:
                description = f"TODO: Add description for {mode}"
                template += f"    {str(mode)!r}: {description!r},\n"
        else:
            template += '\n    # No operating mode values found in device data\n'
            template += '    # Example: "Line": "Grid mode",\n'
        
        template += '''}

# Sensor Title Mappings
# Map API sensor titles to cleaner, standardized display names
SENSOR_TITLE_MAPPINGS = {'''
        
        # Add typo corrections if found
        if analysis.get("potential_typos"):
            template += "\n    # Detected potential typos to fix:\n"
            seen_originals = set()
            for typo_info in analysis["potential_typos"]:
                original = typo_info["original"]
                if original not in seen_originals:
                    seen_originals.add(original)
                    suggested = typo_info["suggested"]
                    template += f"    {str(original)!r}: {str(suggested)!r},\n"

        suggested_mappings = analysis.get("suggested_sensor_title_mappings", {})
        if suggested_mappings:
            template += "\n    # High-confidence cloud/local title matches:\n"
            for original, suggested in sorted(suggested_mappings.items()):
                template += f"    {str(original)!r}: {str(suggested)!r},\n"
        
        template += '''
    # TODO: Add any other sensor name improvements
    # Example: "energyToday": "Daily Energy",
}

# Sensor Value Transformations
# Define functions to transform sensor values if needed
VALUE_TRANSFORMATIONS = {
    # TODO: Add any unit conversions or calculations needed
    # Example: "sensor_name": lambda value: float(value) * 1000,  # Convert kW to W
}

# Export all mappings in standardized structure
# DO NOT MODIFY THIS PART
DEVCODE_CONFIG = {
    "device_info": DEVICE_INFO,
    "output_priority_mapping": OUTPUT_PRIORITY_MAPPING,
    "charger_priority_mapping": CHARGER_PRIORITY_MAPPING,
    "operating_mode_mapping": OPERATING_MODE_MAPPING,
    "sensor_title_mappings": SENSOR_TITLE_MAPPINGS,
    "value_transformations": VALUE_TRANSFORMATIONS,
}
'''
        return template
    
    async def analyze_device_for_devcode(self, device_sn: str) -> Dict[str, Any]:
        """Analyze device data to help create devcode configuration."""
        logger.info("Analyzing selected device for devcode mapping...")
        
        # First try to find device info to get devcode
        device_lookup = await self._find_device_info(device_sn)
        devcode_from_lookup = device_lookup.get("devcode") if device_lookup else None
        collector_alias = device_lookup.get("collector_alias") if device_lookup else "Unknown"
        
        # Get device data
        data_points = await self.get_device_data(device_sn, days=1)
        
        if not data_points:
            logger.warning("No data points found for device")
            return {}
        
        # Find device info
        device_info = {}
        collector_info = {}
        sensor_data = []
        
        for point in data_points:
            if point.get("title") == "Device Info":
                device_info = point
            elif "collector" in point.get("title", "").lower():
                collector_info = point
            else:
                sensor_data.append(point)
        
        # Extract devcode - try multiple sources
        devcode = (device_info.get("devcode") or 
                   collector_info.get("devcode") or 
                   devcode_from_lookup)
        
        # Analyze sensor types and detect patterns
        sensor_analysis = {
            "operating_modes": {},  # value -> count
            "output_priorities": {},
            "charger_priorities": {},
            "sensor_titles": [],
            "unique_sensors": set(),
            "potential_typos": [],
            "unit_patterns": {}
        }
        
        # Common typo patterns to check - full word replacements
        typo_patterns = [
            ("termperature", "temperature"),
            ("devine", "device"),
            ("devise", "device"),
        ]
        
        for point in sensor_data:
            title = point.get("title", "")
            value = point.get("val", "")
            
            sensor_analysis["unique_sensors"].add(title)
            sensor_analysis["sensor_titles"].append(
                {
                    "title": title,
                    "value": value,
                    "unit": point.get("unit", ""),
                }
            )
            
            # Check for typos - only replace exact typo matches
            title_lower = title.lower()
            for typo, correct in typo_patterns:
                if typo in title_lower and correct not in title_lower:
                    # Create proper case-preserving replacement
                    suggested = title
                    # Replace lowercase version
                    if typo in title:
                        suggested = suggested.replace(typo, correct)
                    # Replace capitalized version
                    if typo.capitalize() in title:
                        suggested = suggested.replace(typo.capitalize(), correct.capitalize())
                    # Replace uppercase version
                    if typo.upper() in title:
                        suggested = suggested.replace(typo.upper(), correct.upper())
                    
                    sensor_analysis["potential_typos"].append({
                        "original": title,
                        "suggested": suggested
                    })
            
            # Detect units in values (W, V, A, Hz, °C, %, kWh, etc.)
            value_str = str(value)
            if any(unit in value_str for unit in ["W", "V", "A", "Hz", "°C", "°F", "%", "kWh", "Wh"]):
                if title not in sensor_analysis["unit_patterns"]:
                    sensor_analysis["unit_patterns"][title] = []
                sensor_analysis["unit_patterns"][title].append(value_str)
            
            # Check for operating modes
            if "operating" in title_lower and "mode" in title_lower:
                mode_val = str(value)
                sensor_analysis["operating_modes"][mode_val] = sensor_analysis["operating_modes"].get(mode_val, 0) + 1
            
            # Check for priorities
            if "priority" in title_lower:
                priority_val = str(value)
                if "output" in title_lower:
                    sensor_analysis["output_priorities"][priority_val] = sensor_analysis["output_priorities"].get(priority_val, 0) + 1
                elif "charg" in title_lower:
                    sensor_analysis["charger_priorities"][priority_val] = sensor_analysis["charger_priorities"].get(priority_val, 0) + 1

        control_entries: List[Dict[str, Any]] = []
        parameter_entries: List[Dict[str, Any]] = []
        if device_lookup:
            pn = device_lookup.get("pn")
            devaddr = device_lookup.get("devaddr")
            devcode_lookup = device_lookup.get("devcode")
            if pn and devaddr and devcode_lookup is not None:
                try:
                    raw_controls = await self.get_device_control_fields(
                        pn, devcode_lookup, devaddr, device_sn
                    )
                    control_entries = sorted(
                        [
                            {
                                "name": name,
                                "type": details.get("type", "value"),
                                "id": details.get("id"),
                                "options": details.get("options"),
                                "unit": details.get("unit"),
                                "hint": details.get("hint"),
                            }
                            for name, details in raw_controls.items()
                        ],
                        key=lambda item: item["name"],
                    )
                except Exception as err:
                    logger.warning("Failed to fetch control fields: %s", err)

                try:
                    raw_parameters = await self.get_device_parameters(
                        pn, devcode_lookup, devaddr, device_sn
                    )
                    parameter_entries = sorted(
                        [
                            {
                                "name": name,
                                "value": details.get("value"),
                                "unit": details.get("unit"),
                                "id": details.get("id"),
                            }
                            for name, details in raw_parameters.items()
                        ],
                        key=lambda item: item["name"],
                    )
                except Exception as err:
                    logger.warning("Failed to fetch device parameters: %s", err)
        
        # Convert to sorted lists and prepare mappings
        analysis_result = {
            "analysis_version": 3,
            "devcode": devcode,
            "device_sn": device_sn,
            "device_identity": "sha256:"
            + hashlib.sha256(device_sn.encode("utf-8")).hexdigest()[:12],
            "collector_identity": (
                "sha256:"
                + hashlib.sha256(str(device_lookup.get("pn", "")).encode("utf-8")).hexdigest()[:12]
                if device_lookup and device_lookup.get("pn")
                else ""
            ),
            "device_address": device_lookup.get("devaddr") if device_lookup else None,
            "collector_alias": collector_alias,
            "total_sensors": len(sensor_analysis["unique_sensors"]),
            "operating_modes": sorted(sensor_analysis["operating_modes"].keys()),
            "output_priorities": sorted(sensor_analysis["output_priorities"].keys()),
            "charger_priorities": sorted(sensor_analysis["charger_priorities"].keys()),
            "sensor_titles": sorted(sensor_analysis["unique_sensors"]),
            "potential_typos": sensor_analysis["potential_typos"],
            "unit_patterns": {k: list(set(v))[:3] for k, v in sensor_analysis["unit_patterns"].items()},  # Show sample units
            "sample_data": sensor_analysis["sensor_titles"][:20],  # First 20 samples for better context
            "control_field_count": len(control_entries),
            "control_fields": control_entries,
            "parameter_count": len(parameter_entries),
            "parameters": parameter_entries,
        }

        # Integrity checksum: HMAC-SHA256 over all fields except device_sn
        # and the checksum itself, so users can obfuscate their SN without
        # breaking verification.
        hashable = {k: v for k, v in analysis_result.items() if k != "device_sn"}
        digest = hmac.new(
            b"dessmonitor-analysis-v2",
            json.dumps(hashable, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        analysis_result["checksum"] = digest

        logger.info(f"Analysis complete for devcode {devcode}")
        logger.info(f"Found {analysis_result['total_sensors']} unique sensor types")
        if sensor_analysis["potential_typos"]:
            logger.info(f"Found {len(sensor_analysis['potential_typos'])} potential typos in sensor names")
        
        return analysis_result


def setup_argparser() -> argparse.ArgumentParser:
    """Setup command line argument parser."""
    parser = argparse.ArgumentParser(
        description="DessMonitor CLI tool for devcode development",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Auth command
    auth_parser = subparsers.add_parser("auth", help="Authenticate with DessMonitor API")
    auth_parser.add_argument("--username", required=True, help="DessMonitor username")
    auth_parser.add_argument(
        "--password",
        help="DessMonitor password (omit to enter it without shell-history exposure)",
    )
    auth_parser.add_argument("--company-key", required=True, help="Company key")
    
    # Collectors command
    collectors_parser = subparsers.add_parser("collectors", help="List all data collectors")
    collectors_parser.add_argument("--raw", action="store_true", help="Print raw JSON response")
    
    # Devices command
    devices_parser = subparsers.add_parser("devices", help="List devices for a collector")
    devices_parser.add_argument("--pn", required=True, help="Collector part number (PN)")
    devices_parser.add_argument("--raw", action="store_true", help="Print raw JSON response")
    
    # Data command  
    data_parser = subparsers.add_parser("data", help="Get device data")
    data_parser.add_argument("--device-sn", required=True, help="Device serial number")
    data_parser.add_argument("--days", type=int, default=1, help="Number of days (default: 1)")
    data_parser.add_argument("--raw", action="store_true", help="Print raw JSON response")

    # SP Key Parameters command
    sp_parser = subparsers.add_parser("sp-keys", help="Query SP key parameters for a device")
    sp_parser.add_argument("--device-sn", required=True, help="Device serial number")
    sp_parser.add_argument("--raw", action="store_true", help="Print raw JSON response")

    # Set Config command
    set_config_parser = subparsers.add_parser("set-config", help="Set a device configuration value")
    set_config_parser.add_argument("--device-sn", required=True, help="Device serial number")
    set_config_parser.add_argument("--param-id", required=True, help="Parameter ID (from analyze command)")
    set_config_parser.add_argument("--value", required=True, help="New value to set")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze device for devcode mapping")
    analyze_parser.add_argument(
        "--device-sn",
        help="Device serial number (optional when --local-report can identify it)",
    )
    analyze_parser.add_argument("--output", help="Output file for analysis results")
    analyze_parser.add_argument("--raw", action="store_true", help="Print raw device data instead of analysis")
    analyze_parser.add_argument("--template", action="store_true", help="Generate devcode template Python file")
    analyze_parser.add_argument(
        "--local-report",
        help="Merge a sanitized local-probe JSON report into the devcode evidence",
    )
    analyze_parser.add_argument(
        "--local-inverter-address",
        type=int,
        default=1,
        help="Inverter address to select from the local report (default: 1)",
    )

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify integrity of an analysis JSON file")
    verify_parser.add_argument("file", help="Path to analysis JSON file")

    # Local, read-only collector probe. This command does not use cloud credentials.
    local_parser = subparsers.add_parser(
        "local-probe",
        help="Probe one EyeBond collector locally using read-only inverter requests",
    )
    local_parser.add_argument(
        "--listen-ip", required=True, help="LAN IPv4 address of this host"
    )
    local_parser.add_argument(
        "--collector-ip", required=True, help="LAN IPv4 address of the collector"
    )
    local_parser.add_argument("--tcp-port", type=int, default=8899)
    local_parser.add_argument("--udp-port", type=int, default=58899)
    local_parser.add_argument(
        "--device-code",
        type=int,
        default=0,
        help="Optional cloud-family or tunnel-code hint (0 auto-detects)",
    )
    local_parser.add_argument("--max-address", type=int, default=16)
    local_parser.add_argument("--timeout", type=float, default=90.0)
    local_parser.add_argument(
        "--probe-timeout",
        type=float,
        default=120.0,
        help="Overall read-only inverter detection deadline in seconds",
    )
    local_parser.add_argument("--expected-product-number", default="")
    local_parser.add_argument("--output", help="Private JSON report path (mode 0600)")
    local_parser.add_argument(
        "--include-identifiers",
        action="store_true",
        help="Include collector IP/product number and inverter serial in the report",
    )
    local_parser.add_argument(
        "--confirm-callback",
        action="store_true",
        help="Confirm a temporary UDP callback request may interrupt a cloud session",
    )

    scan_parser = subparsers.add_parser(
        "local-scan",
        help="Find EyeBond collectors with one bounded LAN callback scan",
    )
    scan_parser.add_argument(
        "--listen-ip", required=True, help="LAN IPv4 address of this host"
    )
    scan_parser.add_argument(
        "--network", help="Optional IPv4 network, limited to /24 or smaller"
    )
    scan_parser.add_argument("--tcp-port", type=int, default=8899)
    scan_parser.add_argument("--udp-port", type=int, default=58899)
    scan_parser.add_argument("--timeout", type=float, default=1.5)
    scan_parser.add_argument(
        "--confirm-callback",
        action="store_true",
        help="Confirm callback discovery may briefly interrupt collector cloud sessions",
    )

    return parser


def _attach_local_evidence(
    analysis: Dict[str, Any], local_report_path: str | None, inverter_address: int
) -> Dict[str, Any]:
    """Merge optional read-only local evidence using the standalone helper."""
    if not local_report_path:
        return analysis
    from evidence import combine_evidence, load_local_report

    return combine_evidence(
        analysis,
        load_local_report(local_report_path),
        inverter_address=inverter_address,
    )


async def _resolve_analysis_device_sn(
    cli: DessMonitorCLI,
    device_sn: str | None,
    local_report_path: str | None,
    inverter_address: int,
) -> str:
    """Resolve a cloud device explicitly or from redacted local route evidence."""
    if device_sn:
        return device_sn
    if not local_report_path:
        raise ValueError("analyze requires --device-sn or --local-report")

    from evidence import load_local_report

    report = load_local_report(local_report_path)
    expected_collector = str(report.get("collector", {}).get("product_number", ""))
    matches: list[str] = []
    for collector in await cli.get_collectors():
        product_number = str(collector.get("pn", ""))
        product_hash = hashlib.sha256(product_number.encode("utf-8")).hexdigest()[:12]
        if expected_collector not in (product_number, f"sha256:{product_hash}"):
            continue
        devices = (await cli.get_devices(product_number)).get("dev", [])
        matches.extend(
            str(device["sn"])
            for device in devices
            if device.get("sn") and device.get("devaddr") == inverter_address
        )
    if len(matches) != 1:
        raise ValueError(
            "local report did not resolve to exactly one cloud device; "
            "provide --device-sn explicitly"
        )
    return matches[0]


async def main():
    """Main CLI entry point."""
    parser = setup_argparser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    if args.command in ("local-probe", "local-scan"):
        from local_probe import run_local_probe, run_local_scan

        try:
            report = (
                await run_local_probe(args)
                if args.command == "local-probe"
                else await run_local_scan(args)
            )
        except Exception as e:
            logger.error(f"Command failed: {e}")
            sys.exit(1)
        print(json.dumps(report, indent=2))
        return

    async with DessMonitorCLI() as cli:
        try:
            if args.command == "auth":
                password = args.password or getpass.getpass("DessMonitor password: ")
                success = await cli.authenticate(args.username, password, args.company_key)
                if not success:
                    sys.exit(1)
            
            elif args.command == "collectors":
                collectors = await cli.get_collectors()
                if args.raw:
                    print(json.dumps(collectors, indent=2))
                else:
                    print("\n=== Data Collectors ===")
                    for collector in collectors:
                        pn = collector.get("pn", "Unknown") 
                        alias = collector.get("alias", "No alias")
                        project = collector.get("project_name", "Unknown")
                        status = "Online" if collector.get("status") == 0 else "Offline"
                        print(f"PN: {pn} | Alias: {alias} | Project: {project} | Status: {status}")
            
            elif args.command == "devices":
                devices_data = await cli.get_devices(args.pn)
                if args.raw:
                    print(json.dumps(devices_data, indent=2))
                else:
                    devices = devices_data.get("dev", [])
                    print(f"\n=== Devices for Collector {args.pn} ===")
                    for device in devices:
                        sn = device.get("sn", "Unknown")
                        devcode = device.get("devcode", "Unknown")
                        devaddr = device.get("devaddr", "Unknown")
                        alias = device.get("alias", "No alias")
                        print(f"SN: {sn} | DevCode: {devcode} | DevAddr: {devaddr} | Alias: {alias}")
            
            elif args.command == "data":
                data = await cli.get_device_data(args.device_sn, args.days)
                if args.raw:
                    print(json.dumps(data, indent=2))
                else:
                    print(f"\n=== Data for Device {args.device_sn} (Last {args.days} day(s)) ===")
                    for point in data:
                        title = point.get("title", "Unknown")
                        value = point.get("val", "N/A")
                        timestamp = point.get("time", "Unknown")
                        print(f"{title}: {value} ({timestamp})")

            elif args.command == "sp-keys":
                resp = await cli.get_sp_key_parameters(args.device_sn)
                dat = resp.get("dat", resp)
                if args.raw:
                    print(json.dumps(resp, indent=2))
                else:
                    print(f"\n=== SP Key Parameters for {args.device_sn} ===")
                    # Try to present common shapes nicely; otherwise dump keys
                    if isinstance(dat, list):
                        for item in dat[:100]:
                            if isinstance(item, dict):
                                name = item.get("name") or item.get("key") or item.get("title") or "(unnamed)"
                                desc = item.get("desc") or item.get("description") or ""
                                print(f"- {name}: {desc}")
                            else:
                                print(f"- {item}")
                    elif isinstance(dat, dict):
                        # If server returns {"keys": [...]}
                        keys_list = dat.get("keys")
                        if isinstance(keys_list, list):
                            for key in keys_list[:200]:
                                print(f"- {key}")
                        else:
                            for k, v in list(dat.items())[:100]:
                                print(f"- {k}: {v if isinstance(v, (str, int, float)) else type(v).__name__}")
                    else:
                        print(dat)
            
            elif args.command == "set-config":
                resp = await cli.set_device_control_value(args.device_sn, args.param_id, args.value)
                print(json.dumps(resp, indent=2))
                if resp.get("err") == 0:
                    print(f"\n✅ Successfully set param {args.param_id} to {args.value}")
                else:
                    print(f"\n❌ Failed to set param: {resp.get('desc')}")
            
            elif args.command == "analyze":
                resolved_device_sn = await _resolve_analysis_device_sn(
                    cli,
                    args.device_sn,
                    args.local_report,
                    args.local_inverter_address,
                )
                if args.raw:
                    # For raw mode, just get and print the device data
                    data = await cli.get_device_data(resolved_device_sn, 1)
                    if args.output:
                        _write_private_json(args.output, data)
                        print(f"Raw data saved to {args.output}")
                    else:
                        print(json.dumps(data, indent=2))
                elif args.template:
                    # Generate Python devcode template file
                    analysis = await cli.analyze_device_for_devcode(
                        resolved_device_sn
                    )
                    analysis = _attach_local_evidence(
                        analysis, args.local_report, args.local_inverter_address
                    )
                    template_content = cli.generate_devcode_template(analysis)
                    
                    devcode = analysis.get("devcode", "XXXX")
                    if args.output:
                        output_file = args.output
                    else:
                        output_file = f"devcode_{devcode}.py"
                    
                    _write_private_file(output_file, template_content)
                    
                    print(f"\n✅ Generated devcode template: {output_file}")
                    print(f"   Devcode: {devcode}")
                    print(f"   Sensors: {analysis.get('total_sensors')}")
                    if analysis.get("local_evidence"):
                        local_evidence = analysis["local_evidence"]
                        print(
                            "   Local: "
                            f"{local_evidence.get('profile')} / "
                            f"{local_evidence.get('model')}"
                        )
                    
                    if analysis.get("potential_typos"):
                        print(f"\n⚠️  Found {len(analysis['potential_typos'])} potential typos:")
                        for typo in analysis['potential_typos'][:3]:  # Show first 3
                            print(f"   - {typo['original']} → {typo['suggested']}")
                    
                    print(f"\nNext steps:")
                    print(f"1. Review and update TODO items in {output_file}")
                    print(f"2. Test with your collector")
                    print(f"3. Copy to custom_components/dessmonitor/device_support/")
                    print(f"4. Submit a PR to ha-dessmonitor repository")
                else:
                    analysis = await cli.analyze_device_for_devcode(
                        resolved_device_sn
                    )
                    analysis = _attach_local_evidence(
                        analysis, args.local_report, args.local_inverter_address
                    )
                    
                    output_data = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "analysis": analysis
                    }
                    
                    if args.output:
                        _write_private_json(args.output, output_data)
                        print(f"Analysis saved to {args.output}")
                    else:
                        print(json.dumps(output_data, indent=2))

            elif args.command == "verify":
                with open(args.file, "r") as f:
                    data = json.load(f)

                analysis = data.get("analysis", data)
                stored = analysis.get("checksum")
                if not stored:
                    print("No checksum found - this is a v1 analysis (pre-checksum).")
                    sys.exit(0)

                hashable = {k: v for k, v in analysis.items()
                            if k not in ("device_sn", "checksum")}
                expected = hmac.new(
                    b"dessmonitor-analysis-v2",
                    json.dumps(hashable, sort_keys=True,
                               separators=(",", ":")).encode(),
                    hashlib.sha256,
                ).hexdigest()

                if hmac.compare_digest(stored, expected):
                    print("Checksum OK - analysis data is intact.")
                else:
                    print("Checksum MISMATCH - analysis data has been modified.")
                    sys.exit(1)

        except Exception as e:
            logger.error(f"Command failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
