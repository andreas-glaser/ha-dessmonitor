"""API client for DessMonitor."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import aiohttp
import async_timeout

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
        self.base_url = "http://api.dessmonitor.com/public/"

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

        try:
            async with async_timeout.timeout(30):
                async with self._session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()

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

        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP request failed for action '%s': %s", action, err)
            raise DessMonitorError(f"Request failed: {err}") from err

    async def authenticate(self) -> bool:
        """Authenticate with the DessMonitor API."""
        _LOGGER.debug("Starting authentication process for user: %s", self.username)
        try:
            # Clear existing tokens for re-authentication
            self.token = None
            self.secret = None
            self.token_expire = None
            _LOGGER.debug("Cleared existing authentication tokens")

            auth_params = {
                "usr": self.username,
                "company-key": self.company_key,
                "source": "1",
                "_app_client_": "web",
                "_app_id_": "dessmonitor-api-client",
                "_app_version_": "1.0.0",
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

                # The API returns expiration as duration in seconds, not absolute timestamp
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
            # First try to get projects which contain collectors
            _LOGGER.debug("Querying projects to discover collectors")
            projects_response = await self._make_request(
                "queryPlants", {"pagesize": 50}
            )

            if "dat" in projects_response and "plant" in projects_response["dat"]:
                projects = projects_response["dat"]["plant"]
                _LOGGER.debug("Found %d projects", len(projects))

                # For each project, query its collectors with pagination
                for project in projects:
                    pid = project.get("pid")
                    if pid:
                        try:
                            _LOGGER.debug("Querying collectors for project ID: %s", pid)

                            # Handle pagination - keep fetching until we get all collectors
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

                                        # Check if we've got all collectors
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

            # If no collectors found via projects, try direct collector query
            if not collectors:
                _LOGGER.debug(
                    "No collectors found via projects, trying direct collector query"
                )
                try:
                    direct_response = await self._make_request("queryCollectorCountEs")
                    if "dat" in direct_response:
                        # This might give us collector count or basic info to work with
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
            # Fallback: return empty list rather than hardcoded PNs

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


class DessMonitorError(Exception):
    """Exception raised for DessMonitor API errors."""
