"""Home Assistant integration for Veloretti vehicles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VelorettiClient, VelorettiTokens
from .const import (
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SESSION_UUID,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    SCAN_INTERVAL_MINUTE_OPTIONS,
)
from .coordinator import VelorettiCoordinator

PLATFORMS = (Platform.DEVICE_TRACKER, Platform.IMAGE, Platform.SENSOR)


@dataclass(slots=True)
class VelorettiRuntimeData:
    """Runtime objects shared by Veloretti platforms."""

    client: VelorettiClient
    coordinator: VelorettiCoordinator
    scan_interval_minutes: int


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
    scan_interval_minutes = _scan_interval_minutes_from_options(entry)
    coordinator.async_set_scan_interval(timedelta(minutes=scan_interval_minutes))

    entry.runtime_data = VelorettiRuntimeData(
        client=client,
        coordinator=coordinator,
        scan_interval_minutes=scan_interval_minutes,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: VelorettiConfigEntry,
) -> bool:
    """Unload Veloretti platforms for a config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant,
    entry: VelorettiConfigEntry,
) -> None:
    """Reload only when the user changes options that affect runtime behavior.

    The Veloretti API regularly returns refreshed tokens, and those tokens are
    persisted in the config entry data. Home Assistant calls update listeners for
    data updates as well, so this guard prevents token persistence from
    repeatedly reloading the integration.
    """

    scan_interval_minutes = _scan_interval_minutes_from_options(entry)
    if scan_interval_minutes == entry.runtime_data.scan_interval_minutes:
        return

    await hass.config_entries.async_reload(entry.entry_id)


def _scan_interval_minutes_from_options(entry: VelorettiConfigEntry) -> int:
    """Return the configured polling interval in minutes."""

    minutes = entry.options.get(
        CONF_SCAN_INTERVAL_MINUTES,
        DEFAULT_SCAN_INTERVAL_MINUTES,
    )
    if isinstance(minutes, str) and minutes.isdecimal():
        minutes = int(minutes)

    if minutes not in SCAN_INTERVAL_MINUTE_OPTIONS:
        minutes = DEFAULT_SCAN_INTERVAL_MINUTES

    return minutes
