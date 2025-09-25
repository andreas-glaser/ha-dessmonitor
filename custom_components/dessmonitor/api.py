"""API client for DessMonitor."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import aiohttp
import async_timeout

from .const import API_BASE_URL, UNITS

_LOGGER = logging.getLogger(__name__)


class DessMonitorAPI:
    """DessMonitor API client."""

    def __init__(
        self,
        username: str,
        password: str,
        company_key: str = "bnrl_frRFjEz8Mkn",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.company_key = company_key
        self.base_url = API_BASE_URL

        self._session = session
        self._close_session = False

        self.token: str | None = None
        self.secret: str | None = None
        self.token_expire: int | None = None

        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True

    async def close(self) -> None:
        """Close the session."""
        if self._session and self._close_session:
            await self._session.close()

    def _sha1(self, data: str) -> str:
        """Generate SHA-1 hash."""
        return hashlib.sha1(data.encode()).hexdigest().lower()

    def _rc4_encrypt(self, key: str, data: str) -> bytes:
        """RC4 encryption (simplified for auth)."""
        key_bytes = key.encode()
        data_bytes = data.encode()

        result = bytearray()
        for i, byte in enumerate(data_bytes):
            result.append(byte ^ key_bytes[i % len(key_bytes)])

        return bytes(result)

    def _generate_signature(self, salt: str, action_string: str) -> str:
        """Generate API signature."""
        if self.token and self.secret:
            signature_string = f"{salt}{self.secret}{self.token}{action_string}"
        else:
            pwd_sha1 = self._sha1(self.password)
            signature_string = f"{salt}{pwd_sha1}{action_string}"

        return self._sha1(signature_string)

    def _is_token_expired(self) -> bool:
        """Check if the token is expired."""
        if not self.token_expire:
            return False
        current_time = int(time.time())
        expired = current_time >= self.token_expire
        _LOGGER.debug(
            "Token expiration check: current=%d, expires=%d, expired=%s",
            current_time,
            self.token_expire,
            expired,
        )
        return expired

    async def _make_request(
        self, action: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make API request."""
        if not self._session:
            raise RuntimeError("Session not initialized")

        if action != "authSource" and self._is_token_expired():
            _LOGGER.info("Token expired for action '%s', re-authenticating...", action)
            await self.authenticate()

        salt = str(int(time.time() * 1000))

        action_string = f"&action={action}"
        if params:
            for key, value in params.items():
                action_string += f"&{key}={value}"

        signature = self._generate_signature(salt, action_string)

        url = f"{self.base_url}?sign={signature}&salt={salt}"
        if self.token and action != "authSource":
            url += f"&token={self.token}"
        url += action_string

        _LOGGER.debug(
            "Making %s request with %d parameters", action, len(params) if params else 0
        )
        _LOGGER.debug("Request URL: %s", url)

        timeout_seconds = 30

        try:
            async with async_timeout.timeout(timeout_seconds):
                async with self._session.get(url) as response:
                    try:
                        response.raise_for_status()
                    except aiohttp.ClientResponseError as err:
                        _LOGGER.error(
                            "HTTP %s error for action '%s': %s",
                            err.status,
                            action,
                            err.message,
                        )
                        raise

                    try:
                        data = await response.json()
                    except aiohttp.ContentTypeError:
                        text_preview = await response.text()
                        _LOGGER.error(
                            "Invalid JSON response for action '%s': %s",
                            action,
                            text_preview[:500],
                        )
                        raise DessMonitorError("Invalid response from server")

                    if data.get("err", 0) != 0:
                        error_code = data.get("err")
                        error_msg = data.get("desc", f"API error {error_code}")
                        _LOGGER.error(
                            "API returned error %s for action '%s': %s",
                            error_code,
                            action,
                            error_msg,
                        )
                        raise DessMonitorError(error_msg)

                    return data

        except asyncio.TimeoutError as err:
            _LOGGER.error(
                "API request for action '%s' timed out after %ss", action, timeout_seconds
            )
            raise DessMonitorError("Request timed out") from err
        except aiohttp.ClientResponseError as err:
            raise DessMonitorError(
                f"Server returned HTTP {err.status}: {err.message or 'Unknown error'}"
            ) from err
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP request failed for action '%s': %s", action, err)
            raise DessMonitorError(f"Request failed: {err}") from err

    async def authenticate(self) -> bool:
        """Authenticate with the DessMonitor API."""
        _LOGGER.debug("Starting authentication process for user: %s", self.username)
        try:
            self.token = None
            self.secret = None
            self.token_expire = None
            _LOGGER.debug("Cleared existing authentication tokens")

            auth_params = {
                "usr": self.username,
                "company-key": self.company_key,
                "source": "1",
                "_app_client_": "web",
                "_app_id_": "ha-dessmonitor",
                "_app_version_": "1.1.0",
            }
            _LOGGER.debug(
                "Authentication parameters: %s",
                {k: v if k != "usr" else "***" for k, v in auth_params.items()},
            )

            response = await self._make_request("authSource", auth_params)

            if "dat" in response:
                data = response["dat"]
                self.token = data.get("token")
                self.secret = data.get("secret")
                expire_duration = data.get("expire")

                _LOGGER.debug(
                    "Authentication response data keys: %s", list(data.keys())
                )
                _LOGGER.debug("Token received: %s", "Yes" if self.token else "No")
                _LOGGER.debug("Secret received: %s", "Yes" if self.secret else "No")
                _LOGGER.debug("Expire duration: %s seconds", expire_duration)

                if expire_duration:
                    self.token_expire = int(time.time()) + expire_duration
                    _LOGGER.debug(
                        "Token will expire at timestamp: %d (in %d seconds)",
                        self.token_expire,
                        expire_duration,
                    )
                else:
                    self.token_expire = None
                    _LOGGER.warning("No expiration duration provided by API")

                _LOGGER.info(
                    "Successfully authenticated with DessMonitor API, token valid for %d seconds, expires at: %s",
                    expire_duration or 0,
                    self.token_expire,
                )
                return True

            raise DessMonitorError("No authentication data received")

        except Exception as err:
            _LOGGER.error("Authentication failed for user %s: %s", self.username, err)
            _LOGGER.debug("Authentication error details", exc_info=True)
            raise DessMonitorError(f"Authentication failed: {err}") from err

    async def get_collectors(self) -> list[dict[str, Any]]:
        """Get list of collectors (inverters) via API discovery."""
        _LOGGER.debug("Fetching collectors list via API discovery")
        collectors = []

        try:
            _LOGGER.debug("Querying projects to discover collectors")
            projects_response = await self._make_request(
                "queryPlants", {"pagesize": 50}
            )

            if "dat" in projects_response and "plant" in projects_response["dat"]:
                projects = projects_response["dat"]["plant"]
                _LOGGER.debug("Found %d projects", len(projects))

                for project in projects:
                    pid = project.get("pid")
                    if pid:
                        try:
                            _LOGGER.debug("Querying collectors for project ID: %s", pid)

                            page = 0
                            pagesize = 50  # Request up to 50 collectors per page
                            total_collectors = 0

                            while True:
                                collectors_response = await self._make_request(
                                    "webQueryCollectorsEs",
                                    {"pid": pid, "page": page, "pagesize": pagesize},
                                )

                                if "dat" in collectors_response:
                                    dat = collectors_response["dat"]
                                    project_collectors = dat.get("collector", [])
                                    total_from_api = dat.get("total", 0)
                                    current_page_size = len(project_collectors)

                                    if project_collectors:
                                        collectors.extend(project_collectors)
                                        total_collectors += current_page_size
                                        _LOGGER.debug(
                                            "Found %d collectors in project %s (page %d), total so far: %d/%d",
                                            current_page_size,
                                            pid,
                                            page,
                                            total_collectors,
                                            total_from_api,
                                        )

                                        if (
                                            total_collectors >= total_from_api
                                            or current_page_size < pagesize
                                        ):
                                            break

                                        page += 1
                                    else:
                                        break
                                else:
                                    break

                            _LOGGER.info(
                                "Retrieved %d total collectors for project %s",
                                total_collectors,
                                pid,
                            )

                        except Exception as err:
                            _LOGGER.warning(
                                "Failed to get collectors for project %s: %s", pid, err
                            )

            if not collectors:
                _LOGGER.debug(
                    "No collectors found via projects, trying direct collector query"
                )
                try:
                    direct_response = await self._make_request("queryCollectorCountEs")
                    if "dat" in direct_response:
                        _LOGGER.debug(
                            "Direct collector query response: %s",
                            (
                                list(direct_response["dat"].keys())
                                if isinstance(direct_response["dat"], dict)
                                else "non-dict response"
                            ),
                        )

                except Exception as err:
                    _LOGGER.warning("Direct collector query failed: %s", err)

        except Exception as err:
            _LOGGER.error("Failed to discover collectors via API: %s", err)
            _LOGGER.debug("Collector discovery error details", exc_info=True)

        _LOGGER.info("Successfully discovered %d collectors via API", len(collectors))
        return collectors

    async def get_collector_devices(self, pn: str) -> dict[str, Any]:
        """Get devices under a collector."""
        _LOGGER.debug("Fetching devices for collector PN: %s", pn)
        response = await self._make_request("queryCollectorDevices", {"pn": pn})

        devices_data = response.get("dat", {})
        device_count = len(devices_data.get("dev", []))
        _LOGGER.debug("Found %d devices for collector %s", device_count, pn)

        if device_count > 0:
            for i, device in enumerate(devices_data.get("dev", [])):
                _LOGGER.debug(
                    "Device %d: SN=%s, devcode=%s, devaddr=%s",
                    i,
                    device.get("sn"),
                    device.get("devcode"),
                    device.get("devaddr"),
                )

        return devices_data

    async def get_device_last_data(
        self, pn: str, devcode: int, devaddr: int, sn: str
    ) -> list[dict[str, Any]]:
        """Get latest device data."""
        _LOGGER.debug(
            "Fetching device data: pn=%s, devcode=%s, devaddr=%s, sn=%s",
            pn,
            devcode,
            devaddr,
            sn,
        )

        params = {
            "pn": pn,
            "devcode": devcode,
            "devaddr": devaddr,
            "sn": sn,
            "i18n": "en",
        }

        response = await self._make_request("queryDeviceLastData", params)
        device_data = response.get("dat", [])

        _LOGGER.debug("Retrieved %d data points for device %s", len(device_data), sn)

        if device_data and _LOGGER.isEnabledFor(logging.DEBUG):
            data_types = [d.get("title", "Unknown") for d in device_data]
            _LOGGER.debug("Data point types for device %s: %s", sn, data_types)

        return device_data

    async def get_device_summary_data(self, pid: int) -> dict[str, dict[str, Any]]:
        """Get device summary data from webQueryDeviceEs API."""
        _LOGGER.debug("Fetching device summary data for project ID: %s", pid)

        response = await self._make_request(
            "webQueryDeviceEs", {"pid": pid, "pagesize": 50}
        )

        project_data = response.get("dat", {})
        devices = project_data.get("device", [])

        _LOGGER.debug("Retrieved summary data for %d devices", len(devices))

        summary_data = {}
        for device in devices:
            sn = device.get("sn")
            if sn:
                device_summary = []
                device_alias = device.get("devalias", "Unknown")

                if "outpower" in device:
                    device_summary.append(
                        {
                            "title": "outpower",
                            "val": device["outpower"],
                            "unit": UNITS["POWER_KW"],
                        }
                    )
                    _LOGGER.debug(
                        "Added Total PV Power for %s (%s): %s kW",
                        device_alias,
                        sn,
                        device["outpower"],
                    )

                if "energyToday" in device:
                    device_summary.append(
                        {
                            "title": "energyToday",
                            "val": device["energyToday"],
                            "unit": UNITS["ENERGY"],
                        }
                    )
                    _LOGGER.debug(
                        "Added Energy Today for %s (%s): %s kWh",
                        device_alias,
                        sn,
                        device["energyToday"],
                    )

                if "energyTotal" in device:
                    device_summary.append(
                        {
                            "title": "energyTotal",
                            "val": device["energyTotal"],
                            "unit": UNITS["ENERGY"],
                        }
                    )
                    _LOGGER.debug(
                        "Added Energy Total for %s (%s): %s kWh",
                        device_alias,
                        sn,
                        device["energyTotal"],
                    )

                summary_data[sn] = {
                    "data": device_summary,
                    "device": {
                        "alias": device.get("devalias", "DessMonitor"),
                        "sn": sn,
                        "status": device.get("status", 0),
                    },
                }

                _LOGGER.debug(
                    "Summary data for device %s: %d data points",
                    sn,
                    len(device_summary),
                )

        return summary_data

    async def get_device_control_fields(
        self, pn: str, devcode: int, devaddr: int, sn: str
    ) -> dict[str, Any]:
        """Get device control fields (configuration options)."""
        _LOGGER.debug("Fetching device control fields for device: %s", sn)

        response = await self._make_request(
            "queryDeviceCtrlField",
            {
                "i18n": "en_US",
                "source": "1",
                "pn": pn,
                "devcode": devcode,
                "devaddr": devaddr,
                "sn": sn,
            },
        )

        control_data = response.get("dat", {})
        fields = control_data.get("field", [])

        _LOGGER.debug("Retrieved %d control fields for device %s", len(fields), sn)

        config_settings = {}

        for field in fields:
            field_name = field.get("name", "")
            field_id = field.get("id", "")

            if any(
                keyword in field_name.lower()
                for keyword in [
                    "battery",
                    "charge",
                    "voltage",
                    "current",
                    "priority",
                    "protection",
                    "bulk",
                    "floating",
                    "cutoff",
                    "type",
                    "output",
                ]
            ):

                if "item" in field and field["item"]:
                    options = {}
                    for item in field["item"]:
                        key = item.get("key", "")
                        val = item.get("val", "")
                        options[key] = val

                    config_settings[field_name] = {
                        "id": field_id,
                        "type": "options",
                        "options": options,
                    }
                else:
                    config_settings[field_name] = {"id": field_id, "type": "value"}

                _LOGGER.debug("Added control field: %s (%s)", field_name, field_id)

        return config_settings

    async def get_device_parameters(
        self, pn: str, devcode: int, devaddr: int, sn: str
    ) -> dict[str, Any]:
        """Get device parameters (current parameter values)."""
        _LOGGER.debug("Fetching device parameters for device: %s", sn)

        response = await self._make_request(
            "queryDeviceParsEs",
            {
                "i18n": "en_US",
                "source": "1",
                "pn": pn,
                "devcode": devcode,
                "devaddr": devaddr,
                "sn": sn,
            },
        )

        param_data = response.get("dat", {})
        parameters = param_data.get("parameter", [])

        _LOGGER.debug("Retrieved %d parameters for device %s", len(parameters), sn)

        param_settings = {}

        for param in parameters:
            param_name = param.get("name", "")
            param_value = param.get("val", "")
            param_unit = param.get("unit", "")
            param_id = param.get("par", "")

            param_settings[param_name] = {
                "value": param_value,
                "unit": param_unit,
                "id": param_id,
            }

            _LOGGER.debug(
                "Added parameter: %s = %s %s", param_name, param_value, param_unit
            )

        return param_settings


class DessMonitorError(Exception):
    """Exception raised for DessMonitor API errors."""
