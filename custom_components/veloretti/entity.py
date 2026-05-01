"""Shared entity helpers for the Veloretti integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VelorettiCoordinator


def vehicle_name(vehicle: dict[str, Any]) -> str:
    """Return the user-facing vehicle name used for entities."""

    name = vehicle.get("name")
    if isinstance(name, str) and name:
        return name

    model = vehicle.get("model")
    if isinstance(model, dict) and isinstance(model.get("name"), str):
        return model["name"]

    return "Veloretti"


def vehicle_device_info(vehicle: dict[str, Any], vehicle_uuid: str) -> DeviceInfo:
    """Return Home Assistant device registry information for a vehicle."""

    model = vehicle.get("model")
    model_name = model.get("name") if isinstance(model, dict) else None
    vin = vehicle.get("vin")

    return DeviceInfo(
        identifiers={(DOMAIN, vehicle_uuid)},
        manufacturer="Veloretti",
        model=model_name if isinstance(model_name, str) else None,
        name=vehicle_name(vehicle),
        serial_number=vin if isinstance(vin, str) and vin else None,
    )


class VelorettiVehicleEntity(CoordinatorEntity[VelorettiCoordinator]):
    """Base class for entities that belong to a single Veloretti vehicle."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VelorettiCoordinator, vehicle_uuid: str) -> None:
        """Bind the entity to one vehicle in the coordinator payload."""

        super().__init__(coordinator)
        self.vehicle_uuid = vehicle_uuid

    @property
    def vehicle(self) -> dict[str, Any]:
        """Return the latest vehicle payload for this entity."""

        return self.coordinator.data.vehicles[self.vehicle_uuid]

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry information for the vehicle."""

        return vehicle_device_info(self.vehicle, self.vehicle_uuid)
