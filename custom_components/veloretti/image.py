"""Image platform for Veloretti vehicle dashboard images."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VelorettiConfigEntry
from .coordinator import VelorettiCoordinator
from .entity import VelorettiVehicleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VelorettiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Veloretti vehicle image entities from a config entry."""

    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        VelorettiVehicleImageEntity(coordinator, vehicle_uuid)
        for vehicle_uuid in coordinator.data.vehicles
    )


class VelorettiVehicleImageEntity(VelorettiVehicleEntity, ImageEntity):
    """Dashboard image entity backed by the locally cached Veloretti model image."""

    _attr_content_type = "image/png"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "vehicle_image"

    def __init__(
        self,
        coordinator: VelorettiCoordinator,
        vehicle_uuid: str,
    ) -> None:
        """Create the dashboard image entity for one Veloretti vehicle."""

        super().__init__(coordinator, vehicle_uuid)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_unique_id = f"{vehicle_uuid}_vehicle_image"

    @property
    def image_last_updated(self) -> datetime | None:
        """Return when the cached vehicle image was last refreshed."""

        return self.coordinator.data.vehicle_image_last_updated.get(self.vehicle_uuid)

    async def async_image(self) -> bytes | None:
        """Return the locally cached vehicle image bytes for Home Assistant."""

        return await self.coordinator.async_read_vehicle_image(self.vehicle_uuid)
