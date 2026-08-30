"""Config flow for the Magna Energia iPortal integration.

Unlike diportal (reCAPTCHA -> external session-capture tool), Magna Energia's login page
has no captcha, so username/password can be entered directly in the normal HA config-flow
UI. Home Assistant stores them in its own encrypted config-entry storage - they never touch
disk as a file this integration writes itself.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CHART_TYPE_STACKED,
    DELIVERY_POINTS,
    DOMAIN,
    GRANULARITY_HOUR,
    INTERVAL_DAY,
)
from .coordinator import MagnaAuthError, MagnaConnectionError, async_load, async_login

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


async def _validate_credentials(hass, username: str, password: str) -> None:
    """Raise ValueError with a user-facing reason if login (or a basic data call) fails."""
    session = async_create_clientsession(hass)
    try:
        try:
            await async_login(session, username, password)
        except MagnaAuthError as err:
            raise ValueError("invalid_auth") from err
        except MagnaConnectionError as err:
            raise ValueError("cannot_connect") from err

        # Also confirm the rest of the pipeline (ajax/load.php) actually works for this
        # account, using the cheapest possible call (today's hourly view for the main point).
        try:
            today = datetime.date.today().isoformat()
            await async_load(
                session,
                DELIVERY_POINTS["spotreba"]["eic_index"],
                INTERVAL_DAY,
                GRANULARITY_HOUR,
                CHART_TYPE_STACKED,
                today,
            )
        except MagnaConnectionError as err:
            raise ValueError("cannot_connect") from err
    finally:
        await session.close()


class MagnaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Magna Energia iPortal."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate_credentials(
                    self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except ValueError as err:
                errors["base"] = str(err)
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Magna Energia ({user_input[CONF_USERNAME]})",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=_schema(), errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                await _validate_credentials(
                    self.hass, reauth_entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except ValueError as err:
                errors["base"] = str(err)
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"username": reauth_entry.data[CONF_USERNAME]},
        )
