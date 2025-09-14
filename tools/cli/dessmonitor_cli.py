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
import hashlib
import json
import logging
import os
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


class DessMonitorCLI:
    """DessMonitor API client for CLI usage."""
    
    def __init__(self):
        self.base_url = "http://api.dessmonitor.com/public/"
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.secret: Optional[str] = None
        self.token_expires: Optional[int] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.company_key: Optional[str] = None
        self.config_file = Path(__file__).parent / ".dessmonitor_cli_config.json"
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
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
        
        logger.debug(f"API Request: {action} -> {url}")
        
        async with self.session.get(url) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}: {await response.text()}")
            
            data = await response.json()
            logger.debug(f"API Response: {data}")
            
            if data.get("err") != 0:
                error_msg = data.get("desc", "Unknown API error")
                raise Exception(f"API Error: {error_msg} (code: {data.get('err')})")
            
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
            logger.debug(f"Authentication response: {response}")
            
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
                
                with open(self.config_file, "w") as f:
                    json.dump(config, f, indent=2)
                
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
    
    async def get_collectors(self) -> List[Dict[str, Any]]:
        """Get all collectors/data collectors."""
        collectors = []
        
        # Get projects first
        projects_response = await self._make_request("queryPlants", {"pagesize": "50"})
        
        logger.debug(f"Projects response: {projects_response}")
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
            logger.debug(f"Direct collector response: {direct_response}")
            
            # This endpoint might return collector count, not actual collectors
            # Let's also try the queryCollectorList endpoint
            try:
                list_response = await self._make_request("queryCollectorList")
                logger.debug(f"Collector list response: {list_response}")
                
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
                logger.debug(f"Error checking collector {pn} for device {device_sn}: {e}")
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
            logger.debug(f"Device {device_sn} not found in collectors, trying direct query")
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
            raise Exception(f"Unable to retrieve data for device {device_sn}")

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
    
    def generate_devcode_template(self, analysis: Dict[str, Any]) -> str:
        """Generate a devcode template file based on analysis results."""
        devcode = analysis.get("devcode", "XXXX")
        collector_alias = analysis.get("collector_alias", "Unknown Collector")
        
        template = f'''"""Device support for DessMonitor devcode {devcode}.

AUTO-GENERATED TEMPLATE - Please review and update all mappings!
Generated from device: {analysis.get("device_sn", "Unknown")}
Collector: {collector_alias}
Date: {time.strftime("%Y-%m-%d %H:%M:%S")}

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
    "name": "{collector_alias} (devcode {devcode})",
    "description": "TODO: Add description of your data collector/gateway device",
    "manufacturer": "DessMonitor",  # TODO: Update if different
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
                template += f'    "{priority}": "TODO: Add description for {priority}",\n'
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
                template += f'    "{priority}": "TODO: Add description for {priority}",\n'
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
                template += f'    "{mode}": "TODO: Add description for {mode}",\n'
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
                    template += f'    "{original}": "{suggested}",\n'
        
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
        logger.info(f"Analyzing device {device_sn} for devcode mapping...")
        
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
            sensor_analysis["sensor_titles"].append({"title": title, "value": value})
            
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
        
        # Convert to sorted lists and prepare mappings
        analysis_result = {
            "devcode": devcode,
            "device_sn": device_sn,
            "collector_alias": collector_alias,
            "total_sensors": len(sensor_analysis["unique_sensors"]),
            "operating_modes": sorted(sensor_analysis["operating_modes"].keys()),
            "output_priorities": sorted(sensor_analysis["output_priorities"].keys()),
            "charger_priorities": sorted(sensor_analysis["charger_priorities"].keys()),
            "sensor_titles": sorted(sensor_analysis["unique_sensors"]),
            "potential_typos": sensor_analysis["potential_typos"],
            "unit_patterns": {k: list(set(v))[:3] for k, v in sensor_analysis["unit_patterns"].items()},  # Show sample units
            "sample_data": sensor_analysis["sensor_titles"][:20]  # First 20 samples for better context
        }
        
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
    auth_parser.add_argument("--password", required=True, help="DessMonitor password")
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
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze device for devcode mapping")
    analyze_parser.add_argument("--device-sn", required=True, help="Device serial number")
    analyze_parser.add_argument("--output", help="Output file for analysis results")
    analyze_parser.add_argument("--raw", action="store_true", help="Print raw device data instead of analysis")
    analyze_parser.add_argument("--template", action="store_true", help="Generate devcode template Python file")
    
    return parser


async def main():
    """Main CLI entry point."""
    parser = setup_argparser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    async with DessMonitorCLI() as cli:
        try:
            if args.command == "auth":
                success = await cli.authenticate(args.username, args.password, args.company_key)
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
            
            elif args.command == "analyze":
                if args.raw:
                    # For raw mode, just get and print the device data
                    data = await cli.get_device_data(args.device_sn, 1)
                    if args.output:
                        with open(args.output, "w") as f:
                            json.dump(data, f, indent=2)
                        print(f"Raw data saved to {args.output}")
                    else:
                        print(json.dumps(data, indent=2))
                elif args.template:
                    # Generate Python devcode template file
                    analysis = await cli.analyze_device_for_devcode(args.device_sn)
                    template_content = cli.generate_devcode_template(analysis)
                    
                    devcode = analysis.get("devcode", "XXXX")
                    if args.output:
                        output_file = args.output
                    else:
                        output_file = f"devcode_{devcode}.py"
                    
                    with open(output_file, "w") as f:
                        f.write(template_content)
                    
                    print(f"\n✅ Generated devcode template: {output_file}")
                    print(f"   Devcode: {devcode}")
                    print(f"   Device: {analysis.get('device_sn')}")
                    print(f"   Sensors: {analysis.get('total_sensors')}")
                    
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
                    analysis = await cli.analyze_device_for_devcode(args.device_sn)
                    
                    output_data = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "analysis": analysis
                    }
                    
                    if args.output:
                        with open(args.output, "w") as f:
                            json.dump(output_data, f, indent=2)
                        print(f"Analysis saved to {args.output}")
                    else:
                        print(json.dumps(output_data, indent=2))
        
        except Exception as e:
            logger.error(f"Command failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
