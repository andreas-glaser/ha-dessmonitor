"""API client for DessMonitor."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import aiohttp
import async_timeout
from homeassistant.helpers.storage import Store

from .const import API_BASE_URL, UNITS, VERSION

_LOGGER = logging.getLogger(__name__)


class DessMonitorAPI:
    """DessMonitor API client."""

    def __init__(
        self,
        username: str,
        password: str,
        company_key: str = "bnrl_frRFjEz8Mkn",
        session: aiohttp.ClientSession | None = None,
        store: Store | None = None,
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
        self._store = store

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
        self._ensure_session()
        await self._ensure_token(action)

        salt = str(int(time.time() * 1000))
        action_string = self._build_action_string(action, params)
        signature = self._generate_signature(salt, action_string)
        url = self._build_request_url(action, salt, signature, action_string)

        _LOGGER.debug(
            "Making %s request with %d parameters", action, len(params) if params else 0
        )
        _LOGGER.debug("Request URL: %s", url)

        response_data = await self._fetch_json(action, url)
        return self._validate_api_response(action, response_data)

    def _ensure_session(self) -> None:
        """Ensure that an aiohttp session is available."""
        if not self._session:
            raise RuntimeError("Session not initialized")

    async def _ensure_token(self, action: str) -> None:
        """Refresh authentication token when required."""
        if action == "authSource":
            return
        if self._is_token_expired():
            _LOGGER.info("Token expired for action '%s', re-authenticating...", action)
            await self.authenticate()

    def _build_action_string(self, action: str, params: dict[str, Any] | None) -> str:
        """Construct action string used by the API."""
        action_string = f"&action={action}"
        if params:
            for key, value in params.items():
                action_string += f"&{key}={value}"
        return action_string

    def _build_request_url(
        self, action: str, salt: str, signature: str, action_string: str
    ) -> str:
        """Construct the full request URL including token when available."""
        url = f"{self.base_url}?sign={signature}&salt={salt}"
        if self.token and action != "authSource":
            url += f"&token={self.token}"
        return f"{url}{action_string}"

    async def _fetch_json(self, action: str, url: str) -> dict[str, Any]:
        """Execute HTTP GET and return JSON payload."""
        assert self._session is not None
        timeout_seconds = 30

        try:
            async with async_timeout.timeout(timeout_seconds):
                async with self._session.get(url) as response:
                    response.raise_for_status()
                    try:
                        return await response.json()
                    except aiohttp.ContentTypeError as err:
                        text_preview = await response.text()
                        _LOGGER.error(
                            "Invalid JSON response for action '%s': %s",
                            action,
                            text_preview[:500],
                        )
                        raise DessMonitorError("Invalid response from server") from err
        except asyncio.TimeoutError as err:
            _LOGGER.error(
                "API request for action '%s' timed out after %ss",
                action,
                timeout_seconds,
            )
            raise DessMonitorError("Request timed out") from err
        except asyncio.CancelledError as err:
            _LOGGER.error(
                "API request for action '%s' was cancelled (likely due to timeout)",
                action,
            )
            raise DessMonitorError("Request cancelled") from err
        except aiohttp.ClientResponseError as err:
            _LOGGER.error(
                "HTTP %s error for action '%s': %s",
                err.status,
                action,
                err.message,
            )
            raise DessMonitorError(
                f"Server returned HTTP {err.status}: {err.message or 'Unknown error'}"
            ) from err
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP request failed for action '%s': %s", action, err)
            raise DessMonitorError(f"Request failed: {err}") from err

    @staticmethod
    def _validate_api_response(action: str, data: dict[str, Any]) -> dict[str, Any]:
        """Validate API payload and raise errors when needed."""
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
                "_app_version_": VERSION,
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

                if self._store and self.token and self.secret and self.token_expire:
                    await self._save_token()

                return True

            raise DessMonitorError("No authentication data received")

        except Exception as err:
            _LOGGER.error("Authentication failed for user %s: %s", self.username, err)
            _LOGGER.debug("Authentication error details", exc_info=True)
            raise DessMonitorError(f"Authentication failed: {err}") from err

    async def load_saved_token(self) -> bool:
        """Load saved token from storage."""
        if not self._store:
            return False

        try:
            data = await self._store.async_load()
        except Exception as err:
            _LOGGER.debug("Failed to load saved token: %s", err)
            return False

        if not data:
            return False

        saved_token = data.get("token")
        saved_secret = data.get("secret")
        saved_expire = data.get("token_expire")

        if not (saved_token and saved_secret and saved_expire):
            _LOGGER.debug("Saved token missing required fields, ignoring cached value")
            await self.clear_saved_token()
            return False

        current_time = int(time.time())
        # Add safety buffer so Home Assistant refreshes the token before expiry
        if current_time >= saved_expire - 300:
            _LOGGER.debug(
                "Saved token expired or about to expire, requesting new token"
            )
            await self.clear_saved_token()
            return False

        self.token = saved_token
        self.secret = saved_secret
        self.token_expire = saved_expire

        remaining = saved_expire - current_time
        _LOGGER.info("Reused saved token, valid for %d more seconds", remaining)
        return True

    async def _save_token(self) -> None:
        """Save current token to storage."""
        if not self._store:
            return

        try:
            await self._store.async_save(
                {
                    "token": self.token,
                    "secret": self.secret,
                    "token_expire": self.token_expire,
                }
            )
            _LOGGER.debug("Token saved to storage")
        except Exception as err:
            _LOGGER.debug("Failed to save token: %s", err)

    async def clear_saved_token(self) -> None:
        """Remove any saved token from storage and reset local state."""
        self.token = None
        self.secret = None
        self.token_expire = None

        if not self._store:
            return

        try:
            await self._store.async_remove()
            _LOGGER.debug("Cleared cached DessMonitor token from storage")
        except FileNotFoundError:
            _LOGGER.debug("Cached DessMonitor token file already removed")
        except Exception as err:
            _LOGGER.debug("Failed to clear cached token: %s", err)

    async def get_collectors(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Get list of collectors (inverters) via API discovery."""
        _LOGGER.debug("Fetching collectors list via API discovery")
        collectors: list[dict[str, Any]] = []

        try:
            projects = await self._query_projects()
            for project in projects:
                pid = project.get("pid")
                if not pid:
                    continue

                project_collectors = await self._fetch_collectors_for_project(pid)
                collectors.extend(project_collectors)

            if not collectors:
                await self._attempt_direct_collector_query()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Failed to discover collectors via API: %s", err)
            _LOGGER.debug("Collector discovery error details", exc_info=True)
            raise

        _LOGGER.info("Successfully discovered %d collectors via API", len(collectors))
        projects_summary = self._build_project_summary(collectors)
        return collectors, projects_summary

    async def _query_projects(self) -> list[dict[str, Any]]:
        """Retrieve project list used for collector discovery."""
        _LOGGER.debug("Querying projects to discover collectors")
        response = await self._make_request("queryPlants", {"pagesize": 50})

        projects = response.get("dat", {}).get("plant", [])
        if projects:
            _LOGGER.debug("Found %d projects", len(projects))
        else:
            _LOGGER.debug("No projects returned from queryPlants")
        return projects

    async def _fetch_collectors_for_project(self, pid: int) -> list[dict[str, Any]]:
        """Fetch all collectors for a given project."""
        _LOGGER.debug("Querying collectors for project ID: %s", pid)
        collectors: list[dict[str, Any]] = []
        page = 0
        pagesize = 50
        total_from_api: int | None = None

        while True:
            response = await self._make_request(
                "webQueryCollectorsEs", {"pid": pid, "page": page, "pagesize": pagesize}
            )

            data = response.get("dat")
            if not data:
                break

            batch = data.get("collector", [])
            total_from_api = total_from_api or data.get("total", 0)
            if not batch:
                break

            collectors.extend(batch)

            _LOGGER.debug(
                "Project %s page %d returned %d collectors (total so far %d/%s)",
                pid,
                page,
                len(batch),
                len(collectors),
                total_from_api if total_from_api is not None else "?",
            )

            if (
                total_from_api is not None and len(collectors) >= total_from_api
            ) or len(batch) < pagesize:
                break

            page += 1

        if collectors:
            _LOGGER.info(
                "Retrieved %d total collectors for project %s", len(collectors), pid
            )
        return collectors

    async def _attempt_direct_collector_query(self) -> None:
        """Fallback query for collectors when project lookup returns nothing."""
        _LOGGER.debug("No collectors found via projects, trying direct collector query")
        try:
            direct_response = await self._make_request("queryCollectorCountEs")
            if "dat" in direct_response:
                _LOGGER.debug(
                    "Direct collector query response keys: %s",
                    (
                        list(direct_response["dat"].keys())
                        if isinstance(direct_response["dat"], dict)
                        else "non-dict response"
                    ),
                )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Direct collector query failed: %s", err)

    @staticmethod
    def _build_project_summary(
        collectors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build summary list of projects present in collector payload."""
        projects: list[dict[str, Any]] = []
        seen_projects: set[int] = set()
        for collector in collectors:
            pid = collector.get("pid")
            if pid is None or pid in seen_projects:
                continue

            projects.append(
                {
                    "pid": pid,
                    "pname": collector.get("pname", "Unknown Project"),
                }
            )
            seen_projects.add(pid)
        return projects

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
