"""Config flow for ServiceM8 Business Dashboard."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ServiceM8ApiClient, ServiceM8ApiError, ServiceM8AuthError
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_INCLUDE_ALERTS,
    CONF_INCLUDE_CUSTOMERS,
    CONF_INCLUDE_HISTORY,
    CONF_INCLUDE_SCHEDULE,
    CONF_INCLUDE_STAFF,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TREND_MONTHS,
    DEFAULT_BASE_URL,
    DEFAULT_INCLUDE_ALERTS,
    DEFAULT_INCLUDE_CUSTOMERS,
    DEFAULT_INCLUDE_HISTORY,
    DEFAULT_INCLUDE_SCHEDULE,
    DEFAULT_INCLUDE_STAFF,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_TREND_MONTHS,
    DEFAULT_NAME,
    DOMAIN,
)


class ServiceM8BusinessDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ServiceM8 Business Dashboard."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = ServiceM8ApiClient(
                session=session,
                api_key=user_input[CONF_API_KEY],
                base_url=user_input[CONF_BASE_URL],
            )
            try:
                probe = await client.async_get_account_probe()
            except ServiceM8AuthError:
                errors["base"] = "invalid_auth"
            except ServiceM8ApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                unique_id = f"{user_input[CONF_BASE_URL]}::{probe['company_count_sample']}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(step_id="user", data_schema=_config_schema(), errors=errors)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return ServiceM8BusinessDashboardOptionsFlow(config_entry)


class ServiceM8BusinessDashboardOptionsFlow(config_entries.OptionsFlow):
    """Handle ServiceM8 options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=_options_schema(self.config_entry))


def _config_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            vol.Required(
                CONF_SCAN_INTERVAL_MINUTES,
                default=DEFAULT_SCAN_INTERVAL_MINUTES,
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=360)),
            vol.Required(CONF_INCLUDE_STAFF, default=DEFAULT_INCLUDE_STAFF): bool,
            vol.Required(CONF_INCLUDE_HISTORY, default=DEFAULT_INCLUDE_HISTORY): bool,
            vol.Required(CONF_INCLUDE_ALERTS, default=DEFAULT_INCLUDE_ALERTS): bool,
            vol.Required(CONF_INCLUDE_CUSTOMERS, default=DEFAULT_INCLUDE_CUSTOMERS): bool,
            vol.Required(CONF_INCLUDE_SCHEDULE, default=DEFAULT_INCLUDE_SCHEDULE): bool,
            vol.Required(CONF_TREND_MONTHS, default=DEFAULT_TREND_MONTHS): vol.All(
                vol.Coerce(int), vol.Range(min=3, max=24)
            ),
        }
    )


def _options_schema(config_entry: config_entries.ConfigEntry) -> vol.Schema:
    options = config_entry.options
    data = config_entry.data
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL_MINUTES,
                default=options.get(CONF_SCAN_INTERVAL_MINUTES, data[CONF_SCAN_INTERVAL_MINUTES]),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=360)),
            vol.Required(
                CONF_INCLUDE_STAFF,
                default=options.get(CONF_INCLUDE_STAFF, data[CONF_INCLUDE_STAFF]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_HISTORY,
                default=options.get(CONF_INCLUDE_HISTORY, data[CONF_INCLUDE_HISTORY]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_ALERTS,
                default=options.get(CONF_INCLUDE_ALERTS, data[CONF_INCLUDE_ALERTS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_CUSTOMERS,
                default=options.get(CONF_INCLUDE_CUSTOMERS, data[CONF_INCLUDE_CUSTOMERS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_SCHEDULE,
                default=options.get(CONF_INCLUDE_SCHEDULE, data[CONF_INCLUDE_SCHEDULE]),
            ): bool,
            vol.Required(
                CONF_TREND_MONTHS,
                default=options.get(CONF_TREND_MONTHS, data[CONF_TREND_MONTHS]),
            ): vol.All(vol.Coerce(int), vol.Range(min=3, max=24)),
        }
    )
