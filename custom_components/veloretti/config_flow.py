"""Config flow for the Veloretti integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import selector

from .api import VelorettiApiError, VelorettiAuthError, VelorettiClient
from .const import (
    CONF_ACCOUNT_UUID,
    CONF_EMAIL,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SESSION_UUID,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    SCAN_INTERVAL_MINUTE_OPTIONS,
)

CONF_CODE = "code"


class VelorettiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Veloretti config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Create the flow state used between the email and code steps."""

        self._email: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for this config entry."""

        return VelorettiOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Ask for the account email and request a magic login code."""

        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip().lower()
            client = VelorettiClient(async_get_clientsession(self.hass))

            try:
                await client.request_magic_code(email)
            except VelorettiApiError:
                errors["base"] = "cannot_connect"
            else:
                self._email = email
                return await self.async_step_code()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_EMAIL): str}),
            errors=errors,
        )

    async def async_step_code(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Exchange the emailed Veloretti code for tokens."""

        errors: dict[str, str] = {}
        if self._email is None:
            return await self.async_step_user()

        if user_input is not None:
            code = user_input[CONF_CODE].strip()
            client = VelorettiClient(async_get_clientsession(self.hass))

            try:
                tokens = await client.exchange_magic_code(self._email, code)
                account = await client.get_account()
            except VelorettiAuthError:
                errors["base"] = "invalid_auth"
            except VelorettiApiError:
                errors["base"] = "cannot_connect"
            else:
                account_uuid = account.get("uuid")
                if isinstance(account_uuid, str):
                    await self.async_set_unique_id(account_uuid)
                    self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=self._email,
                    data={
                        CONF_EMAIL: self._email,
                        CONF_ACCOUNT_UUID: account_uuid,
                        CONF_TOKEN: tokens.token,
                        CONF_REFRESH_TOKEN: tokens.refresh_token,
                        CONF_SESSION_UUID: tokens.session_uuid,
                    },
                )

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required(CONF_CODE): str}),
            errors=errors,
            description_placeholders={CONF_EMAIL: self._email},
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Start a UI reauthentication flow when refresh can no longer recover."""

        self._email = entry_data.get(CONF_EMAIL)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Request a fresh magic code for the existing account."""

        errors: dict[str, str] = {}
        if not isinstance(self._email, str):
            return await self.async_step_user()

        if user_input is not None:
            client = VelorettiClient(async_get_clientsession(self.hass))
            try:
                await client.request_magic_code(self._email)
            except VelorettiApiError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_reauth_code()

        return self.async_show_form(
            step_id="reauth_confirm",
            errors=errors,
            description_placeholders={CONF_EMAIL: self._email},
        )

    async def async_step_reauth_code(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Store replacement tokens after a reauthentication code is entered."""

        errors: dict[str, str] = {}
        if not isinstance(self._email, str):
            return await self.async_step_user()

        if user_input is not None:
            client = VelorettiClient(async_get_clientsession(self.hass))
            try:
                tokens = await client.exchange_magic_code(
                    self._email,
                    user_input[CONF_CODE].strip(),
                )
                account = await client.get_account()
            except VelorettiAuthError:
                errors["base"] = "invalid_auth"
            except VelorettiApiError:
                errors["base"] = "cannot_connect"
            else:
                existing_entry = self._get_reauth_entry()
                self.hass.config_entries.async_update_entry(
                    existing_entry,
                    data={
                        **existing_entry.data,
                        CONF_TOKEN: tokens.token,
                        CONF_REFRESH_TOKEN: tokens.refresh_token,
                        CONF_SESSION_UUID: tokens.session_uuid,
                        CONF_ACCOUNT_UUID: account.get("uuid"),
                    },
                )
                await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_code",
            data_schema=vol.Schema({vol.Required(CONF_CODE): str}),
            errors=errors,
            description_placeholders={CONF_EMAIL: self._email},
        )


class VelorettiOptionsFlow(config_entries.OptionsFlow):
    """Handle Veloretti options that users can change from the UI."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Let the user configure how often Veloretti data is refreshed."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL_MINUTES: int(
                        user_input[CONF_SCAN_INTERVAL_MINUTES]
                    )
                },
            )

        scan_interval_minutes = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES,
            DEFAULT_SCAN_INTERVAL_MINUTES,
        )
        if scan_interval_minutes not in SCAN_INTERVAL_MINUTE_OPTIONS:
            scan_interval_minutes = DEFAULT_SCAN_INTERVAL_MINUTES

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_MINUTES,
                        default=str(scan_interval_minutes),
                    ): selector(
                        {
                            "select": {
                                "options": [
                                    str(option)
                                    for option in SCAN_INTERVAL_MINUTE_OPTIONS
                                ],
                                "mode": "dropdown",
                            }
                        }
                    )
                }
            ),
        )
