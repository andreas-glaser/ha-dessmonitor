"""Config flow for DessMonitor integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DessMonitorAPI, DessMonitorError
from .const import (
    CONF_COMPANY_KEY,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    DEFAULT_COMPANY_KEY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    UPDATE_INTERVAL_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_COMPANY_KEY, default=DEFAULT_COMPANY_KEY): str,
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.In(
            UPDATE_INTERVAL_OPTIONS
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    username = data[CONF_USERNAME]
    company_key = data[CONF_COMPANY_KEY]
    update_interval = data[CONF_UPDATE_INTERVAL]

    _LOGGER.debug(
        "Validating input for user: %s, company_key: %s, interval: %ds",
        username,
        company_key,
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
            _LOGGER.error("Authentication returned False for user: %s", username)
            raise InvalidAuth("Authentication failed")

        _LOGGER.debug("Authentication successful, fetching collectors")
        collectors = await api.get_collectors()
        if not collectors:
            _LOGGER.error("No collectors found for user: %s", username)
            raise CannotConnect("No collectors found")

        _LOGGER.info(
            "Validation successful: user=%s, collectors=%d", username, len(collectors)
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
            "Unexpected exception during validation for user %s: %s", username, err
        )
        raise CannotConnect from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for DessMonitor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        _LOGGER.debug("Config flow step_user called with input: %s", bool(user_input))
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            _LOGGER.debug("Processing config flow for user: %s", username)

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
                    "Unexpected exception in config flow for user %s: %s", username, err
                )
                errors["base"] = "unknown"
            else:
                _LOGGER.debug(
                    "Setting unique ID and creating config entry for: %s", username
                )
                await self.async_set_unique_id(username)
                self._abort_if_unique_id_configured()

                _LOGGER.info(
                    "Successfully created DessMonitor config entry: %s", info["title"]
                )
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        _LOGGER.debug("Showing config form with errors: %s", errors)
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_company_key": DEFAULT_COMPANY_KEY,
            },
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        _LOGGER.debug(
            "Config import requested with data keys: %s", list(import_data.keys())
        )
        return await self.async_step_user(import_data)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlow(config_entry)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for DessMonitor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        _LOGGER.debug(
            "Options flow init called for entry: %s", self.config_entry.entry_id
        )

        if user_input is not None:
            old_interval = self.config_entry.options.get(
                CONF_UPDATE_INTERVAL,
                self.config_entry.data.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                ),
            )
            new_interval = user_input[CONF_UPDATE_INTERVAL]
            _LOGGER.info(
                "Updating DessMonitor options: interval %ds -> %ds",
                old_interval,
                new_interval,
            )
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        _LOGGER.debug(
            "Showing options form with current interval: %ds", current_interval
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=current_interval,
                    ): vol.In(UPDATE_INTERVAL_OPTIONS),
                }
            ),
        )
