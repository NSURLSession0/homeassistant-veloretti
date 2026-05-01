"""Device tracker platform for Veloretti vehicle GPS locations."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VelorettiConfigEntry
from .api import parse_unix_timestamp
from .coordinator import VelorettiCoordinator
from .entity import VelorettiVehicleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VelorettiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Veloretti GPS trackers from a config entry."""

    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        VelorettiDeviceTracker(coordinator, vehicle_uuid)
        for vehicle_uuid in coordinator.data.vehicles
    )


class VelorettiDeviceTracker(VelorettiVehicleEntity, TrackerEntity):
    """GPS tracker backed by Veloretti's vehicle location payload."""

    _attr_icon = "mdi:bicycle"
    _attr_translation_key = "vehicle_location"

    def __init__(
        self,
        coordinator: VelorettiCoordinator,
        vehicle_uuid: str,
    ) -> None:
        """Create the location tracker for one Veloretti vehicle."""

        super().__init__(coordinator, vehicle_uuid)
        self._attr_unique_id = f"{vehicle_uuid}_location"

    @property
    def latitude(self) -> float | None:
        """Return the latest latitude from Veloretti."""

        return _number_value(_location(self.vehicle).get("latitude"))

    @property
    def longitude(self) -> float | None:
        """Return the latest longitude from Veloretti."""

        return _number_value(_location(self.vehicle).get("longitude"))

    @property
    def source_type(self) -> SourceType:
        """Tell Home Assistant this tracker is GPS-based."""

        return SourceType.GPS

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose non-sensitive location metadata."""

        last_update = parse_unix_timestamp(_location(self.vehicle).get("last_update"))
        return {"last_update": last_update.isoformat() if last_update else None}


def _location(vehicle: dict[str, Any]) -> dict[str, Any]:
    """Return the optional location object from a vehicle payload."""

    location = vehicle.get("location")
    return location if isinstance(location, dict) else {}


def _number_value(value: Any) -> float | None:
    """Return a numeric value from Veloretti location fields."""

    return float(value) if isinstance(value, int | float) else None
