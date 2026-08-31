"""Config flow for DessMonitor integration."""

from __future__ import annotations

import logging
from ipaddress import ip_address
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import DessMonitorAPI, DessMonitorError
from .const import (
    CONF_COMPANY_KEY,
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_COLLECTOR_IP,
    CONF_LOCAL_COLLECTOR_IPS,
    CONF_LOCAL_DEVICE_CODE,
    CONF_LOCAL_EXPECTED_PN,
    CONF_LOCAL_LISTEN_IP,
    CONF_LOCAL_MODE,
    CONF_LOCAL_POLL_INTERVAL,
    CONF_LOCAL_REDIRECT_CONFIRMED,
    CONF_LOCAL_TCP_PORT,
    CONF_LOCAL_UDP_PORT,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_HYBRID,
    CONNECTION_TYPE_LOCAL,
    DEFAULT_COMPANY_KEY,
    DEFAULT_LOCAL_DEVICE_CODE,
    DEFAULT_LOCAL_POLL_INTERVAL,
    DEFAULT_LOCAL_TCP_PORT,
    DEFAULT_LOCAL_UDP_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOCAL_MODE_DISABLED,
    LOCAL_MODE_OPTIONS,
    LOCAL_MODE_PREFER_LOCAL,
    LOCAL_POLL_INTERVAL_OPTIONS,
    UPDATE_INTERVAL_OPTIONS,
)
from .local.network import normalize_local_ipv4

_LOGGER = logging.getLogger(__name__)


def _mask_username(value: str) -> str:
    """Mask usernames in logs to protect user identities."""
    value = value.strip()
    if len(value) <= 3:
        return "***"
    return f"{value[:3]}***"


def _list_choice(choices: dict[int, str]) -> vol.All:
    """Build a radio-list choice with stable string values for the frontend."""
    return vol.All(
        vol.Coerce(str),
        SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=str(value), label=label)
                    for value, label in choices.items()
                ],
                mode=SelectSelectorMode.LIST,
            )
        ),
    )


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): vol.All(str, vol.Length(min=1, max=100)),
        vol.Required(CONF_PASSWORD): vol.All(str, vol.Length(min=1, max=100)),
        vol.Optional(CONF_COMPANY_KEY, default=DEFAULT_COMPANY_KEY): vol.All(
            str, vol.Length(min=1, max=100)
        ),
        vol.Optional(
            CONF_UPDATE_INTERVAL, default=str(DEFAULT_UPDATE_INTERVAL)
        ): _list_choice(UPDATE_INTERVAL_OPTIONS),
    }
)


def _local_schema(
    default_listen_ip: str = "",
    *,
    advanced: bool = False,
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build a short default form with a separate expert path."""
    current = defaults or {}
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_LOCAL_LISTEN_IP,
            default=current.get(CONF_LOCAL_LISTEN_IP, default_listen_ip),
        ): str,
        vol.Required(
            CONF_LOCAL_COLLECTOR_IP,
            default=current.get(CONF_LOCAL_COLLECTOR_IP, ""),
        ): str,
        vol.Required(
            CONF_LOCAL_REDIRECT_CONFIRMED,
            default=bool(current.get(CONF_LOCAL_COLLECTOR_IP)),
        ): bool,
    }
    if advanced:
        fields.update(
            {
                vol.Optional(
                    CONF_LOCAL_EXPECTED_PN,
                    default=current.get(CONF_LOCAL_EXPECTED_PN, ""),
                ): vol.All(str, vol.Length(max=64)),
                vol.Optional(
                    CONF_LOCAL_TCP_PORT,
                    default=current.get(CONF_LOCAL_TCP_PORT, DEFAULT_LOCAL_TCP_PORT),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Optional(
                    CONF_LOCAL_UDP_PORT,
                    default=current.get(CONF_LOCAL_UDP_PORT, DEFAULT_LOCAL_UDP_PORT),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Optional(
                    CONF_LOCAL_DEVICE_CODE,
                    default=current.get(
                        CONF_LOCAL_DEVICE_CODE, DEFAULT_LOCAL_DEVICE_CODE
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
                vol.Optional(
                    CONF_LOCAL_POLL_INTERVAL,
                    default=str(
                        current.get(
                            CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL
                        )
                    ),
                ): _list_choice(LOCAL_POLL_INTERVAL_OPTIONS),
            }
        )
    return vol.Schema(fields)


def _validate_local_ipv4(value: str) -> str:
    """Return a normalized RFC1918 or loopback IPv4 address."""
    try:
        return normalize_local_ipv4(value)
    except ValueError as err:
        raise InvalidLocalAddress from err


def _normalize_local_input(
    user_input: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Normalize local settings and return field-specific validation errors."""
    normalized: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field in (CONF_LOCAL_LISTEN_IP, CONF_LOCAL_COLLECTOR_IP):
        try:
            normalized[field] = _validate_local_ipv4(str(user_input[field]))
        except (KeyError, InvalidLocalAddress):
            errors[field] = "invalid_ip"

    if (
        not errors
        and normalized[CONF_LOCAL_LISTEN_IP] == normalized[CONF_LOCAL_COLLECTOR_IP]
    ):
        errors[CONF_LOCAL_COLLECTOR_IP] = "collector_is_home_assistant"

    if not user_input.get(CONF_LOCAL_REDIRECT_CONFIRMED):
        errors[CONF_LOCAL_REDIRECT_CONFIRMED] = "redirect_not_confirmed"

    normalized[CONF_LOCAL_EXPECTED_PN] = str(
        user_input.get(CONF_LOCAL_EXPECTED_PN, "")
    ).strip()
    normalized[CONF_LOCAL_TCP_PORT] = user_input.get(
        CONF_LOCAL_TCP_PORT, DEFAULT_LOCAL_TCP_PORT
    )
    normalized[CONF_LOCAL_UDP_PORT] = user_input.get(
        CONF_LOCAL_UDP_PORT, DEFAULT_LOCAL_UDP_PORT
    )
    normalized[CONF_LOCAL_DEVICE_CODE] = user_input.get(
        CONF_LOCAL_DEVICE_CODE, DEFAULT_LOCAL_DEVICE_CODE
    )
    normalized[CONF_LOCAL_POLL_INTERVAL] = _normalized_choice(
        user_input.get(CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL),
        LOCAL_POLL_INTERVAL_OPTIONS,
        DEFAULT_LOCAL_POLL_INTERVAL,
    )
    return normalized, errors


def _normalize_collector_ips(value: Any, listen_ip: str) -> list[str]:
    """Normalize a short, de-duplicated list of private collector addresses."""
    raw_values = (
        value if isinstance(value, list) else str(value).replace("\n", ",").split(",")
    )
    collector_ips: list[str] = []
    for raw_value in raw_values:
        raw_parts = str(raw_value).split()
        for raw_part in raw_parts:
            collector_ip = _validate_local_ipv4(raw_part)
            if collector_ip == listen_ip:
                raise CollectorIsHomeAssistant
            if collector_ip not in collector_ips:
                collector_ips.append(collector_ip)
    if not collector_ips or len(collector_ips) > 16:
        raise InvalidLocalAddress
    return collector_ips


def _normalize_hybrid_local_input(
    user_input: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate the short hybrid form and apply automatic protocol defaults."""
    current = existing or {}
    errors: dict[str, str] = {}
    try:
        listen_ip = _validate_local_ipv4(user_input[CONF_LOCAL_LISTEN_IP])
    except (KeyError, InvalidLocalAddress):
        errors[CONF_LOCAL_LISTEN_IP] = "invalid_ip"
        listen_ip = ""
    try:
        collector_ips = _normalize_collector_ips(
            user_input[CONF_LOCAL_COLLECTOR_IPS], listen_ip
        )
    except CollectorIsHomeAssistant:
        errors[CONF_LOCAL_COLLECTOR_IPS] = "collector_is_home_assistant"
        collector_ips = []
    except (KeyError, InvalidLocalAddress):
        errors[CONF_LOCAL_COLLECTOR_IPS] = "invalid_ip_list"
        collector_ips = []
    if not user_input.get(CONF_LOCAL_REDIRECT_CONFIRMED):
        errors[CONF_LOCAL_REDIRECT_CONFIRMED] = "redirect_not_confirmed"

    options = {
        CONF_LOCAL_LISTEN_IP: listen_ip,
        CONF_LOCAL_COLLECTOR_IPS: collector_ips,
        CONF_LOCAL_TCP_PORT: current.get(CONF_LOCAL_TCP_PORT, DEFAULT_LOCAL_TCP_PORT),
        CONF_LOCAL_UDP_PORT: current.get(CONF_LOCAL_UDP_PORT, DEFAULT_LOCAL_UDP_PORT),
        CONF_LOCAL_DEVICE_CODE: current.get(
            CONF_LOCAL_DEVICE_CODE, DEFAULT_LOCAL_DEVICE_CODE
        ),
        CONF_LOCAL_POLL_INTERVAL: _normalized_choice(
            user_input.get(
                CONF_LOCAL_POLL_INTERVAL,
                current.get(CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL),
            ),
            LOCAL_POLL_INTERVAL_OPTIONS,
            DEFAULT_LOCAL_POLL_INTERVAL,
        ),
        CONF_LOCAL_EXPECTED_PN: "",
    }
    return options, errors


def _hybrid_local_schema(
    *,
    default_listen_ip: str,
    configured_collectors: Any = "",
    local_poll_interval: int = DEFAULT_LOCAL_POLL_INTERVAL,
    redirect_confirmed: bool | None = None,
) -> vol.Schema:
    """Build the same minimal local-first form for setup and options."""
    if isinstance(configured_collectors, list):
        configured_collectors = ", ".join(configured_collectors)
    return vol.Schema(
        {
            vol.Required(
                CONF_LOCAL_LISTEN_IP,
                default=default_listen_ip,
            ): str,
            vol.Required(
                CONF_LOCAL_COLLECTOR_IPS,
                default=configured_collectors,
            ): str,
            vol.Optional(
                CONF_LOCAL_POLL_INTERVAL,
                default=str(local_poll_interval),
            ): _list_choice(LOCAL_POLL_INTERVAL_OPTIONS),
            vol.Required(
                CONF_LOCAL_REDIRECT_CONFIRMED,
                default=(
                    bool(configured_collectors)
                    if redirect_confirmed is None
                    else redirect_confirmed
                ),
            ): bool,
        }
    )


def _default_local_ip(hass: HomeAssistant) -> str:
    """Use Home Assistant's configured bind address without external lookups."""
    api = hass.config.api
    if api is None:
        return ""
    try:
        value = _validate_local_ipv4(str(api.local_ip))
    except InvalidLocalAddress:
        return ""
    return "" if ip_address(value).is_loopback else value


def _normalized_choice(value: Any, choices: dict[int, str], default: int) -> int:
    """Normalize legacy string choices while rejecting unsupported values."""
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized in choices else default


def _normalize_update_interval(user_input: dict[str, Any]) -> dict[str, Any]:
    """Return cloud input with its frontend choice normalized for storage."""
    return {
        **user_input,
        CONF_UPDATE_INTERVAL: _normalized_choice(
            user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            UPDATE_INTERVAL_OPTIONS,
            DEFAULT_UPDATE_INTERVAL,
        ),
    }


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    username = data[CONF_USERNAME].strip()
    company_key = data[CONF_COMPANY_KEY].strip()
    update_interval = data[CONF_UPDATE_INTERVAL]

    _LOGGER.debug(
        "Validating input for user: %s, interval: %ds",
        _mask_username(username),
        update_interval,
    )

    session = async_get_clientsession(hass)
    api = DessMonitorAPI(
        username=username,
        password=data[CONF_PASSWORD],
        company_key=company_key,
        session=session,
    )

    try:
        _LOGGER.debug("Attempting authentication during config validation")
        success = await api.authenticate()
        if not success:
            _LOGGER.error(
                "Authentication returned False for user: %s",
                _mask_username(username),
            )
            raise InvalidAuth("Authentication failed")

        _LOGGER.debug("Authentication successful, fetching collectors")
        collectors, _projects = await api.get_collectors()
        if not collectors:
            _LOGGER.error("No collectors found for user: %s", _mask_username(username))
            raise CannotConnect("No collectors found")

        _LOGGER.info(
            "Validation successful: user=%s, collectors=%d",
            _mask_username(username),
            len(collectors),
        )
        return {
            "title": f"DessMonitor ({username})",
            "collectors_count": len(collectors),
        }
    except DessMonitorError as err:
        error_msg = str(err).lower()
        _LOGGER.error("DessMonitor API error during validation: %s", err)
        if "password" in error_msg or "auth" in error_msg:
            raise InvalidAuth from err
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception(
            "Unexpected exception during validation for user %s: %s",
            _mask_username(username),
            err,
        )
        raise CannotConnect from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for DessMonitor."""

    # New local/hybrid settings are optional and legacy API entries already
    # have the canonical schema. Keep version 1 so existing users do not need
    # a migration or replacement config entry.
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose cloud or local communication."""
        if user_input and CONF_USERNAME in user_input:
            return await self.async_step_cloud(user_input)
        return self.async_show_menu(
            step_id="user",
            menu_options=(
                CONNECTION_TYPE_CLOUD,
                CONNECTION_TYPE_HYBRID,
                CONNECTION_TYPE_LOCAL,
                "local_advanced",
            ),
        )

    async def async_step_hybrid(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure cloud credentials before the recommended local-first step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _normalize_update_interval(user_input)
            username = user_input[CONF_USERNAME]
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Unexpected exception in hybrid setup for user %s",
                    _mask_username(username),
                )
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(username)
                self._abort_if_unique_id_configured()
                self._pending_hybrid_cloud_data = {
                    **user_input,
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD,
                }
                self._pending_hybrid_title = info["title"]
                return await self.async_step_hybrid_local()

        return self.async_show_form(
            step_id="hybrid",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_company_key": DEFAULT_COMPANY_KEY,
            },
        )

    async def async_step_hybrid_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish guided hybrid setup with safe, automatic local defaults."""
        errors: dict[str, str] = {}
        if user_input is not None:
            local_options, errors = _normalize_hybrid_local_input(user_input)
            if not errors:
                cloud_data = getattr(self, "_pending_hybrid_cloud_data", None)
                title = getattr(self, "_pending_hybrid_title", None)
                if not isinstance(cloud_data, dict) or not isinstance(title, str):
                    return self.async_abort(reason="hybrid_setup_expired")
                return self.async_create_entry(
                    title=title,
                    data=cloud_data,
                    options={
                        CONF_LOCAL_MODE: LOCAL_MODE_PREFER_LOCAL,
                        **local_options,
                    },
                )

        form_values = user_input or {}
        return self.async_show_form(
            step_id="hybrid_local",
            data_schema=_hybrid_local_schema(
                default_listen_ip=form_values.get(
                    CONF_LOCAL_LISTEN_IP, _default_local_ip(self.hass)
                ),
                configured_collectors=form_values.get(CONF_LOCAL_COLLECTOR_IPS, ""),
                local_poll_interval=form_values.get(
                    CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL
                ),
                redirect_confirmed=form_values.get(CONF_LOCAL_REDIRECT_CONFIRMED),
            ),
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the existing DessMonitor cloud API."""
        _LOGGER.debug("Config flow step_user called with input: %s", bool(user_input))
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _normalize_update_interval(user_input)
            username = user_input[CONF_USERNAME]
            _LOGGER.debug(
                "Processing config flow for user: %s", _mask_username(username)
            )

            try:
                info = await validate_input(self.hass, user_input)
                _LOGGER.debug("Input validation successful: %s", info)
            except CannotConnect as err:
                _LOGGER.error("Cannot connect error in config flow: %s", err)
                errors["base"] = "cannot_connect"
            except InvalidAuth as err:
                _LOGGER.error("Invalid auth error in config flow: %s", err)
                errors["base"] = "invalid_auth"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Unexpected exception in config flow for user %s: %s",
                    _mask_username(username),
                    err,
                )
                errors["base"] = "unknown"
            else:
                _LOGGER.debug(
                    "Setting unique ID and creating config entry for: %s",
                    _mask_username(username),
                )
                await self.async_set_unique_id(username)
                self._abort_if_unique_id_configured()

                _LOGGER.info(
                    "Successfully created DessMonitor config entry: %s", info["title"]
                )
                return self.async_create_entry(
                    title=info["title"],
                    data={**user_input, CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD},
                )

        _LOGGER.debug("Showing config form with errors: %s", errors)
        return self.async_show_form(
            step_id="cloud",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_company_key": DEFAULT_COMPANY_KEY,
            },
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure targeted, read-only local collector communication."""
        return await self._async_local_form("local", user_input, advanced=False)

    async def async_step_local_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure local mode with protocol and network overrides."""
        return await self._async_local_form("local_advanced", user_input, advanced=True)

    async def _async_local_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        *,
        advanced: bool,
    ) -> ConfigFlowResult:
        """Validate and render a standalone local configuration form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized, errors = _normalize_local_input(user_input)

            if not errors:
                collector_ip = normalized[CONF_LOCAL_COLLECTOR_IP]
                await self.async_set_unique_id(f"local:{collector_ip}")
                self._abort_if_unique_id_configured()
                data = {
                    **normalized,
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,
                }
                return self.async_create_entry(
                    title=f"DessMonitor Local ({collector_ip})", data=data
                )

        return self.async_show_form(
            step_id=step_id,
            data_schema=_local_schema(_default_local_ip(self.hass), advanced=advanced),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the core network settings of a standalone local entry."""
        entry = self._get_reconfigure_entry()
        if entry.data.get(CONF_CONNECTION_TYPE) != CONNECTION_TYPE_LOCAL:
            return self.async_abort(reason="reconfigure_cloud_in_options")

        errors: dict[str, str] = {}
        if user_input is not None:
            normalized, errors = _normalize_local_input(user_input)
            if not errors:
                collector_ip = normalized[CONF_LOCAL_COLLECTOR_IP]
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"local:{collector_ip}",
                    title=f"DessMonitor Local ({collector_ip})",
                    data={**entry.data, **normalized},
                )

        defaults = {**entry.data, **(user_input or {})}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_local_schema(
                _default_local_ip(self.hass), advanced=True, defaults=defaults
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle import from configuration.yaml."""
        _LOGGER.debug(
            "Config import requested with data keys: %s", list(import_data.keys())
        )
        return await self.async_step_cloud(import_data)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlow(config_entry)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidLocalAddress(HomeAssistantError):
    """Error to indicate a local address is unsafe or malformed."""


class CollectorIsHomeAssistant(HomeAssistantError):
    """Error to indicate a callback target points back to Home Assistant."""


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for DessMonitor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        _LOGGER.debug(
            "Options flow init called for entry: %s", self._config_entry.entry_id
        )

        connection_type = self._config_entry.data.get(
            CONF_CONNECTION_TYPE, CONNECTION_TYPE_CLOUD
        )
        if connection_type == CONNECTION_TYPE_LOCAL:
            return await self.async_step_local(user_input)

        if user_input is not None:
            user_input = _normalize_update_interval(user_input)
            old_interval = self._config_entry.options.get(
                CONF_UPDATE_INTERVAL,
                self._config_entry.data.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                ),
            )
            new_interval = user_input[CONF_UPDATE_INTERVAL]
            _LOGGER.info(
                "Updating DessMonitor options: interval %ds -> %ds",
                old_interval,
                new_interval,
            )
            if user_input[CONF_LOCAL_MODE] == LOCAL_MODE_PREFER_LOCAL:
                self._pending_options = user_input
                return await self.async_step_hybrid_local()
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self._config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_interval = _normalized_choice(
            current_interval, UPDATE_INTERVAL_OPTIONS, DEFAULT_UPDATE_INTERVAL
        )
        _LOGGER.debug(
            "Showing options form with current interval: %ds", current_interval
        )
        current_local_mode = self._config_entry.options.get(
            CONF_LOCAL_MODE, LOCAL_MODE_DISABLED
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=str(current_interval),
                    ): _list_choice(UPDATE_INTERVAL_OPTIONS),
                    vol.Optional(CONF_LOCAL_MODE, default=current_local_mode): vol.In(
                        LOCAL_MODE_OPTIONS
                    ),
                }
            ),
        )

    async def async_step_hybrid_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the optional preferred-local transport for a cloud entry."""
        errors: dict[str, str] = {}
        existing = {**self._config_entry.data, **self._config_entry.options}
        if user_input is not None:
            local_options, errors = _normalize_hybrid_local_input(user_input, existing)
            if not errors:
                return self.async_create_entry(
                    title="", data={**self._pending_options, **local_options}
                )

        form_values = {**existing, **(user_input or {})}
        default_listen_ip = form_values.get(CONF_LOCAL_LISTEN_IP) or _default_local_ip(
            self.hass
        )
        configured_collectors = form_values.get(CONF_LOCAL_COLLECTOR_IPS)
        if not configured_collectors:
            configured_collectors = form_values.get(CONF_LOCAL_COLLECTOR_IP, "")
        return self.async_show_form(
            step_id="hybrid_local",
            data_schema=_hybrid_local_schema(
                default_listen_ip=default_listen_ip,
                configured_collectors=configured_collectors,
                local_poll_interval=form_values.get(
                    CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL
                ),
                redirect_confirmed=form_values.get(CONF_LOCAL_REDIRECT_CONFIRMED),
            ),
            errors=errors,
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the local poll interval."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_LOCAL_POLL_INTERVAL: _normalized_choice(
                        user_input.get(
                            CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL
                        ),
                        LOCAL_POLL_INTERVAL_OPTIONS,
                        DEFAULT_LOCAL_POLL_INTERVAL,
                    )
                },
            )
        current = self._config_entry.options.get(
            CONF_LOCAL_POLL_INTERVAL,
            self._config_entry.data.get(
                CONF_LOCAL_POLL_INTERVAL, DEFAULT_LOCAL_POLL_INTERVAL
            ),
        )
        current = _normalized_choice(
            current, LOCAL_POLL_INTERVAL_OPTIONS, DEFAULT_LOCAL_POLL_INTERVAL
        )
        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_LOCAL_POLL_INTERVAL, default=str(current)
                    ): _list_choice(LOCAL_POLL_INTERVAL_OPTIONS)
                }
            ),
        )
