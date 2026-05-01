"""Home Assistant integration for Veloretti vehicles."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VelorettiClient, VelorettiTokens
from .const import (
    CONF_REFRESH_TOKEN,
    CONF_SESSION_UUID,
    CONF_TOKEN,
)
from .coordinator import VelorettiCoordinator

PLATFORMS = (Platform.DEVICE_TRACKER, Platform.SENSOR)


@dataclass(slots=True)
class VelorettiRuntimeData:
    """Runtime objects shared by Veloretti platforms."""

    client: VelorettiClient
    coordinator: VelorettiCoordinator


type VelorettiConfigEntry = ConfigEntry[VelorettiRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VelorettiConfigEntry,
) -> bool:
    """Set up Veloretti from a config entry."""

    async def async_store_tokens(tokens: VelorettiTokens) -> None:
        """Persist refreshed tokens without logging or exposing them."""

        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_TOKEN: tokens.token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_SESSION_UUID: tokens.session_uuid,
            },
        )

    session = async_get_clientsession(hass)
    client = VelorettiClient(
        session,
        token=entry.data.get(CONF_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        session_uuid=entry.data.get(CONF_SESSION_UUID),
        on_tokens_updated=async_store_tokens,
    )
    coordinator = VelorettiCoordinator(hass, entry, client)

    entry.runtime_data = VelorettiRuntimeData(client=client, coordinator=coordinator)

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: VelorettiConfigEntry,
) -> bool:
    """Unload Veloretti platforms for a config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
