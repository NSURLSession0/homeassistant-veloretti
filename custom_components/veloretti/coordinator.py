"""Coordinator for Veloretti vehicle data."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VelorettiAuthError, VelorettiClient, VelorettiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class VelorettiCoordinatorData:
    """Latest account and vehicle data fetched from Veloretti."""

    account: dict[str, Any]
    vehicles: dict[str, dict[str, Any]]


class VelorettiCoordinator(DataUpdateCoordinator[VelorettiCoordinatorData]):
    """Fetch account and vehicle data for Veloretti entities."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: VelorettiClient,
    ) -> None:
        """Create the shared data coordinator for a config entry."""

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> VelorettiCoordinatorData:
        """Fetch the overview first, then enrich every vehicle with detail data."""

        try:
            account = await self.client.get_account()
            vehicle_overviews = account.get("vehicles") or {}
            vehicles: dict[str, dict[str, Any]] = {}

            if not isinstance(vehicle_overviews, dict):
                vehicle_overviews = {}

            for vehicle_uuid, vehicle_overview in vehicle_overviews.items():
                if not isinstance(vehicle_uuid, str):
                    continue

                vehicle_detail = await self.client.get_vehicle(vehicle_uuid)

                # Component firmware currently only appears in the account
                # overview, so the detail object keeps that subtree attached for
                # diagnostic firmware entities.
                if isinstance(vehicle_overview, dict) and isinstance(
                    vehicle_overview.get("components"), dict
                ):
                    vehicle_detail["components"] = vehicle_overview["components"]

                vehicles[vehicle_uuid] = vehicle_detail

        except VelorettiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VelorettiError as err:
            raise UpdateFailed(str(err)) from err

        return VelorettiCoordinatorData(account=account, vehicles=vehicles)
