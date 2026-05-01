"""Sensor platform for Veloretti vehicles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import Platform, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VelorettiConfigEntry
from .api import parse_iso_datetime, parse_unix_timestamp
from .const import DOMAIN
from .coordinator import VelorettiCoordinator
from .entity import VelorettiVehicleEntity


@dataclass(frozen=True, kw_only=True)
class VelorettiSensorEntityDescription(SensorEntityDescription):
    """Describe one vehicle-level sensor and how to read it from API data."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_DESCRIPTIONS: tuple[VelorettiSensorEntityDescription, ...] = (
    VelorettiSensorEntityDescription(
        key="odometer_km",
        translation_key="odometer",
        icon="mdi:speedometer",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda vehicle: _meters_to_kilometers(vehicle.get("odometer")),
    ),
    VelorettiSensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:bicycle-electric",
        value_fn=lambda vehicle: vehicle.get("status"),
    ),
    VelorettiSensorEntityDescription(
        key="sim_status",
        translation_key="sim_status",
        icon="mdi:sim",
        value_fn=lambda vehicle: vehicle.get("sim_status"),
    ),
    VelorettiSensorEntityDescription(
        key="location_last_update",
        translation_key="location_last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda vehicle: parse_unix_timestamp(
            _nested_value(vehicle, "location", "last_update")
        ),
    ),
    VelorettiSensorEntityDescription(
        key="maintenance_status",
        translation_key="maintenance_status",
        icon="mdi:wrench-clock",
        value_fn=lambda vehicle: _nested_value(vehicle, "maintenance", "status"),
    ),
    VelorettiSensorEntityDescription(
        key="maintenance_days_until",
        translation_key="maintenance_days_until",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda vehicle: _nested_value(
            vehicle, "maintenance", "upcoming", "days_until"
        ),
    ),
    VelorettiSensorEntityDescription(
        key="maintenance_distance_until",
        translation_key="maintenance_distance_until",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        value_fn=lambda vehicle: _meters_to_kilometers(
            _nested_value(vehicle, "maintenance", "upcoming", "meters_until")
        ),
    ),
    VelorettiSensorEntityDescription(
        key="maintenance_upcoming_date",
        translation_key="maintenance_upcoming_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda vehicle: parse_iso_datetime(
            _nested_value(vehicle, "maintenance", "upcoming", "date")
        ),
    ),
    VelorettiSensorEntityDescription(
        key="warranty_status",
        translation_key="warranty_status",
        icon="mdi:shield-check",
        value_fn=lambda vehicle: _nested_value(vehicle, "warranty", "status"),
    ),
    VelorettiSensorEntityDescription(
        key="warranty_expires_at",
        translation_key="warranty_expires_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda vehicle: parse_iso_datetime(
            _nested_value(vehicle, "warranty", "expires_at")
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VelorettiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Veloretti sensors from a config entry."""

    coordinator = entry.runtime_data.coordinator
    entity_registry = er.async_get(hass)
    entities: list[SensorEntity] = []

    for vehicle_uuid, vehicle in coordinator.data.vehicles.items():
        _remove_meter_odometer_entity(entity_registry, vehicle_uuid)
        entities.extend(
            VelorettiVehicleSensor(coordinator, vehicle_uuid, description)
            for description in SENSOR_DESCRIPTIONS
        )
        entities.extend(_firmware_entities(coordinator, vehicle_uuid, vehicle))

    async_add_entities(entities)


def _remove_meter_odometer_entity(
    entity_registry: er.EntityRegistry,
    vehicle_uuid: str,
) -> None:
    """Remove the meter-based odometer entity so Home Assistant creates the km entity.

    The integration now exposes odometer values in kilometers. Removing the
    original unique ID prevents Home Assistant from keeping stale meter metadata.
    """

    entity_id = entity_registry.async_get_entity_id(
        Platform.SENSOR,
        DOMAIN,
        f"{vehicle_uuid}_odometer",
    )
    if entity_id:
        entity_registry.async_remove(entity_id)


class VelorettiVehicleSensor(VelorettiVehicleEntity, SensorEntity):
    """Sensor that reads one value from a Veloretti vehicle payload."""

    entity_description: VelorettiSensorEntityDescription

    def __init__(
        self,
        coordinator: VelorettiCoordinator,
        vehicle_uuid: str,
        description: VelorettiSensorEntityDescription,
    ) -> None:
        """Create a sensor bound to one vehicle and one data key."""

        super().__init__(coordinator, vehicle_uuid)
        self.entity_description = description
        self._attr_unique_id = f"{vehicle_uuid}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the latest native sensor value."""

        return self.entity_description.value_fn(self.vehicle)


class VelorettiFirmwareSensor(CoordinatorEntity[VelorettiCoordinator], SensorEntity):
    """Diagnostic sensor for a component firmware field."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: VelorettiCoordinator,
        vehicle_uuid: str,
        component_uuid: str,
        component_name: str,
        field: str,
    ) -> None:
        """Create a firmware sensor without exposing component serial numbers."""

        super().__init__(coordinator)
        self.vehicle_uuid = vehicle_uuid
        self.component_uuid = component_uuid
        self.field = field
        self._attr_translation_key = f"firmware_{field}"
        self._attr_translation_placeholders = {"component": component_name}
        self._attr_unique_id = f"{vehicle_uuid}_{component_uuid}_firmware_{field}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach firmware sensors to the parent vehicle device."""

        from .const import DOMAIN
        from .entity import vehicle_name

        vehicle = self.coordinator.data.vehicles[self.vehicle_uuid]
        model = vehicle.get("model")
        model_name = model.get("name") if isinstance(model, dict) else None
        return DeviceInfo(
            identifiers={(DOMAIN, self.vehicle_uuid)},
            manufacturer="Veloretti",
            model=model_name if isinstance(model_name, str) else None,
            name=vehicle_name(vehicle),
        )

    @property
    def native_value(self) -> str | None:
        """Return the latest firmware version or status for this component."""

        component = _component(
            self.coordinator.data.vehicles[self.vehicle_uuid],
            self.component_uuid,
        )
        firmware = component.get("firmware") if isinstance(component, dict) else None
        if not isinstance(firmware, dict):
            return None

        if self.field == "status":
            status = firmware.get("status")
            return status if isinstance(status, str) else None

        current = firmware.get("current")
        if isinstance(current, dict) and isinstance(current.get("version"), str):
            return current["version"]

        return None


def _firmware_entities(
    coordinator: VelorettiCoordinator,
    vehicle_uuid: str,
    vehicle: dict[str, Any],
) -> list[VelorettiFirmwareSensor]:
    """Create firmware sensors for components present in Veloretti data."""

    components = vehicle.get("components")
    if not isinstance(components, dict):
        return []

    entities: list[VelorettiFirmwareSensor] = []
    for component_uuid, component in components.items():
        if not isinstance(component_uuid, str) or not isinstance(component, dict):
            continue

        firmware = component.get("firmware")
        component_name = component.get("name")
        if not isinstance(firmware, dict) or not isinstance(component_name, str):
            continue

        if isinstance(firmware.get("status"), str):
            entities.append(
                VelorettiFirmwareSensor(
                    coordinator,
                    vehicle_uuid,
                    component_uuid,
                    component_name,
                    "status",
                )
            )

        current = firmware.get("current")
        if isinstance(current, dict) and isinstance(current.get("version"), str):
            entities.append(
                VelorettiFirmwareSensor(
                    coordinator,
                    vehicle_uuid,
                    component_uuid,
                    component_name,
                    "version",
                )
            )

    return entities


def _component(vehicle: dict[str, Any], component_uuid: str) -> dict[str, Any]:
    """Return one component object from a vehicle payload."""

    components = vehicle.get("components")
    if not isinstance(components, dict):
        return {}

    component = components.get(component_uuid)
    return component if isinstance(component, dict) else {}


def _nested_value(data: dict[str, Any], *keys: str) -> Any:
    """Read a nested API value while tolerating missing optional objects."""

    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _meters_to_kilometers(value: Any) -> float | None:
    """Convert Veloretti meter values to kilometer values for Home Assistant."""

    if not isinstance(value, int | float):
        return None

    return value / 1000
