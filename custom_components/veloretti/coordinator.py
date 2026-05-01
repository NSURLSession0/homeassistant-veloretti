"""Coordinator for Veloretti vehicle data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VelorettiApiError, VelorettiAuthError, VelorettiClient, VelorettiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, IMAGE_DOWNLOAD_TIMEOUT_SECONDS
from .image_store import (
    VelorettiCachedImage,
    VelorettiVehicleImageStore,
    image_cache_key,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class VelorettiCoordinatorData:
    """Latest account and vehicle data fetched from Veloretti."""

    account: dict[str, Any]
    vehicles: dict[str, dict[str, Any]]
    vehicle_image_paths: dict[str, str]
    vehicle_image_last_updated: dict[str, datetime]


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
        self._image_store = VelorettiVehicleImageStore(hass)
        self._image_cache_keys: dict[str, str] = {}
        self._vehicle_images: dict[str, VelorettiCachedImage] = {}

    def async_set_scan_interval(self, scan_interval: timedelta) -> None:
        """Apply the user-configured polling interval to future refreshes."""

        self.update_interval = scan_interval

    async def _async_update_data(self) -> VelorettiCoordinatorData:
        """Fetch the overview first, then enrich every vehicle with detail data."""

        try:
            account = await self.client.get_account()
            vehicle_overviews = account.get("vehicles") or {}
            vehicles: dict[str, dict[str, Any]] = {}
            vehicle_image_paths: dict[str, str] = {}
            vehicle_image_last_updated: dict[str, datetime] = {}

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

                cached_image = await self._async_update_vehicle_image(
                    vehicle_uuid,
                    _vehicle_model_image_url(vehicle_detail),
                )
                if cached_image:
                    vehicle_image_paths[vehicle_uuid] = cached_image.public_path
                    vehicle_image_last_updated[vehicle_uuid] = cached_image.updated_at

                vehicles[vehicle_uuid] = vehicle_detail

        except VelorettiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VelorettiError as err:
            raise UpdateFailed(str(err)) from err

        return VelorettiCoordinatorData(
            account=account,
            vehicles=vehicles,
            vehicle_image_paths=vehicle_image_paths,
            vehicle_image_last_updated=vehicle_image_last_updated,
        )

    async def async_read_vehicle_image(self, vehicle_uuid: str) -> bytes | None:
        """Read the cached vehicle image for the Home Assistant image entity."""

        return await self._image_store.async_read(vehicle_uuid)

    async def _async_update_vehicle_image(
        self,
        vehicle_uuid: str,
        image_url: str | None,
    ) -> VelorettiCachedImage | None:
        """Cache the vehicle image locally and return its cache metadata."""

        if image_url is None:
            self._image_cache_keys.pop(vehicle_uuid, None)
            self._vehicle_images.pop(vehicle_uuid, None)
            return None

        cache_key = image_cache_key(image_url)
        file_exists = await self._image_store.async_exists(vehicle_uuid)
        cached_image = self._vehicle_images.get(vehicle_uuid)
        if (
            self._image_cache_keys.get(vehicle_uuid) == cache_key
            and file_exists
            and cached_image is not None
        ):
            return cached_image

        try:
            # The model image is useful for dashboards, but it must not hold up
            # Home Assistant setup when the signed S3 URL is slow or unavailable.
            async with asyncio.timeout(IMAGE_DOWNLOAD_TIMEOUT_SECONDS):
                image_content = await self.client.download_vehicle_image(image_url)
            cached_image = await self._image_store.async_store(
                vehicle_uuid,
                image_content,
            )
        except (TimeoutError, OSError, VelorettiApiError):
            # Image updates are optional presentation data. Vehicle state remains
            # usable when the signed URL expires early or the local cache write fails.
            _LOGGER.warning(
                "Could not update Veloretti vehicle image for %s",
                vehicle_uuid,
                exc_info=True,
            )
            if file_exists:
                return await self._image_store.async_metadata(vehicle_uuid)

            return None

        self._image_cache_keys[vehicle_uuid] = cache_key
        self._vehicle_images[vehicle_uuid] = cached_image
        return cached_image


def _vehicle_model_image_url(vehicle: dict[str, Any]) -> str | None:
    """Return the signed model image URL from a vehicle payload."""

    model = vehicle.get("model")
    if not isinstance(model, dict):
        return None

    image_url = model.get("image")
    return image_url if isinstance(image_url, str) and image_url else None
