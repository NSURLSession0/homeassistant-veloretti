"""Fast unit tests for Veloretti entity metadata and image helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import tempfile
import unittest
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "veloretti"


def _install_homeassistant_stubs() -> None:
    """Install the Home Assistant stubs needed by dependency-light tests."""

    homeassistant = ModuleType("homeassistant")
    sys.modules["homeassistant"] = homeassistant

    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    helpers = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers

    device_registry = ModuleType("homeassistant.helpers.device_registry")
    device_registry.DeviceInfo = dict
    sys.modules["homeassistant.helpers.device_registry"] = device_registry

    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        """Store the coordinator reference like Home Assistant's base entity."""

        def __class_getitem__(cls, _item: Any) -> type[CoordinatorEntity]:
            """Support the generic subscription used by the integration."""

            return cls

        def __init__(self, coordinator: Any) -> None:
            """Bind a fake coordinator to the entity under test."""

            self.coordinator = coordinator

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    entity = ModuleType("homeassistant.helpers.entity")

    class EntityCategory:
        """Small enum-shaped stub for entity categories."""

        DIAGNOSTIC = "diagnostic"

    entity.EntityCategory = EntityCategory
    sys.modules["homeassistant.helpers.entity"] = entity

    entity_platform = ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.EntityRegistry = object
    entity_registry.async_get = lambda _hass: None
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry

    const = ModuleType("homeassistant.const")

    class Platform:
        """Small enum-shaped stub for Home Assistant platforms."""

        SENSOR = "sensor"

    class UnitOfLength:
        """Small enum-shaped stub for length units."""

        KILOMETERS = "km"

    class UnitOfTime:
        """Small enum-shaped stub for time units."""

        DAYS = "d"

    const.Platform = Platform
    const.UnitOfLength = UnitOfLength
    const.UnitOfTime = UnitOfTime
    sys.modules["homeassistant.const"] = const

    components = ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = components

    image = ModuleType("homeassistant.components.image")

    class ImageEntity:
        """Marker class for image entities."""

        def __init__(self, hass: Any) -> None:
            """Store the Home Assistant object like the real image entity."""

            self.hass = hass

    image.ImageEntity = ImageEntity
    sys.modules["homeassistant.components.image"] = image

    sensor = ModuleType("homeassistant.components.sensor")

    class SensorDeviceClass:
        """Small enum-shaped stub for sensor device classes."""

        DISTANCE = "distance"
        DURATION = "duration"
        TIMESTAMP = "timestamp"

    class SensorStateClass:
        """Small enum-shaped stub for sensor state classes."""

        TOTAL_INCREASING = "total_increasing"

    class SensorEntity:
        """Marker class for sensor entities."""

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        """Store the entity description fields used by the integration."""

        key: str
        translation_key: str | None = None
        icon: str | None = None
        native_unit_of_measurement: str | None = None
        device_class: str | None = None
        state_class: str | None = None
        entity_category: str | None = None

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorEntity = SensorEntity
    sensor.SensorEntityDescription = SensorEntityDescription
    sensor.SensorStateClass = SensorStateClass
    sys.modules["homeassistant.components.sensor"] = sensor

    tracker_package = ModuleType("homeassistant.components.device_tracker")
    sys.modules["homeassistant.components.device_tracker"] = tracker_package

    tracker_config_entry = ModuleType(
        "homeassistant.components.device_tracker.config_entry"
    )

    class TrackerEntity:
        """Marker class for tracker entities."""

    tracker_config_entry.TrackerEntity = TrackerEntity
    sys.modules[
        "homeassistant.components.device_tracker.config_entry"
    ] = tracker_config_entry

    tracker_const = ModuleType("homeassistant.components.device_tracker.const")

    class SourceType:
        """Small enum-shaped stub for tracker source types."""

        GPS = "gps"

    tracker_const.SourceType = SourceType
    sys.modules["homeassistant.components.device_tracker.const"] = tracker_const


def _load_veloretti_module(name: str) -> Any:
    """Load one Veloretti module from disk under its package name."""

    spec = importlib.util.spec_from_file_location(
        f"custom_components.veloretti.{name}",
        PACKAGE_PATH / f"{name}.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"custom_components.veloretti.{name}"] = module
    spec.loader.exec_module(module)
    return module


def _load_entity_modules() -> tuple[Any, Any, Any, Any, Any]:
    """Load entity modules with minimal Home Assistant and package stubs."""

    _install_homeassistant_stubs()

    package = ModuleType("custom_components.veloretti")
    package.__path__ = [str(PACKAGE_PATH)]
    package.VelorettiConfigEntry = object
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules["custom_components.veloretti"] = package

    coordinator = ModuleType("custom_components.veloretti.coordinator")
    coordinator.VelorettiCoordinator = object
    sys.modules["custom_components.veloretti.coordinator"] = coordinator

    api = ModuleType("custom_components.veloretti.api")
    api.parse_iso_datetime = lambda _value: None
    api.parse_unix_timestamp = lambda _value: None
    sys.modules["custom_components.veloretti.api"] = api

    _load_veloretti_module("const")
    image_store = _load_veloretti_module("image_store")
    entity = _load_veloretti_module("entity")
    sensor = _load_veloretti_module("sensor")
    device_tracker = _load_veloretti_module("device_tracker")
    image = _load_veloretti_module("image")
    return image_store, entity, sensor, device_tracker, image


class FakeHass:
    """Minimal Home Assistant object for image-store tests."""

    def __init__(self, config_dir: Path) -> None:
        """Create a fake config path root."""

        self.config = SimpleNamespace(path=lambda *parts: str(config_dir.joinpath(*parts)))

    async def async_add_executor_job(self, target: Any, *args: Any) -> Any:
        """Run executor jobs inline for deterministic fast tests."""

        return target(*args)


def _run(coro: Any) -> Any:
    """Run an async helper from a synchronous unittest."""

    return asyncio.run(coro)


class VelorettiEntityTests(unittest.TestCase):
    """Unit tests for Veloretti entity metadata."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the modules once after installing lightweight stubs."""

        (
            cls.image_store,
            cls.entity,
            cls.sensor,
            cls.device_tracker,
            cls.image,
        ) = _load_entity_modules()

    def test_device_info_exposes_vin_as_serial_number(self) -> None:
        """Vehicle device metadata includes the VIN as the serial number."""

        device_info = self.entity.vehicle_device_info(
            {
                "name": "Ace Two",
                "vin": "34004713",
                "model": {"name": "Ace Two"},
            },
            "vehicle-uuid",
        )

        self.assertEqual(device_info["serial_number"], "34004713")
        self.assertEqual(device_info["model"], "Ace Two")

    def test_vin_sensor_reads_vehicle_vin(self) -> None:
        """The diagnostic VIN sensor reads the vehicle VIN from API data."""

        vin_description = next(
            description
            for description in self.sensor.SENSOR_DESCRIPTIONS
            if description.key == "vin"
        )

        self.assertEqual(vin_description.value_fn({"vin": "34004713"}), "34004713")
        self.assertEqual(vin_description.entity_category, "diagnostic")

    def test_device_tracker_does_not_expose_entity_picture(self) -> None:
        """The GPS tracker keeps its bike icon instead of using the vehicle image."""

        coordinator = SimpleNamespace(
            data=SimpleNamespace(
                vehicles={"vehicle-uuid": {"location": {}}},
                vehicle_image_paths={"vehicle-uuid": "/local/veloretti/vehicle-uuid.png"},
            )
        )

        tracker = self.device_tracker.VelorettiDeviceTracker(
            coordinator,
            "vehicle-uuid",
        )

        self.assertIsNone(getattr(tracker, "entity_picture", None))

    def test_image_store_writes_expected_local_file(self) -> None:
        """The image store writes the PNG and updates its refresh timestamp."""

        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.image_store.VelorettiVehicleImageStore(FakeHass(Path(temp_dir)))

            cached_image = _run(store.async_store("vehicle-uuid", b"png"))
            updated_cached_image = _run(store.async_store("vehicle-uuid", b"png2"))

            self.assertEqual(
                cached_image.public_path,
                "/local/veloretti/vehicle-uuid.png",
            )
            self.assertEqual(
                Path(temp_dir, "www", "veloretti", "vehicle-uuid.png").read_bytes(),
                b"png2",
            )
            self.assertGreater(updated_cached_image.updated_at, cached_image.updated_at)
            self.assertEqual(
                _run(store.async_metadata("vehicle-uuid")),
                updated_cached_image,
            )

    def test_image_entity_returns_cached_bytes_and_update_time(self) -> None:
        """The image entity serves cached bytes and reports cache update time."""

        updated_at = object()

        class FakeCoordinator:
            """Coordinator stub with image metadata and read access."""

            hass = None
            data = SimpleNamespace(
                vehicles={"vehicle-uuid": {"location": {}}},
                vehicle_image_last_updated={"vehicle-uuid": updated_at},
            )

            async def async_read_vehicle_image(self, vehicle_uuid: str) -> bytes:
                """Return cached bytes for the requested vehicle."""

                assert vehicle_uuid == "vehicle-uuid"
                return b"png"

        image_entity = self.image.VelorettiVehicleImageEntity(
            FakeCoordinator(),
            "vehicle-uuid",
        )

        self.assertIs(image_entity.hass, None)
        self.assertEqual(image_entity._attr_entity_category, "diagnostic")
        self.assertEqual(image_entity.image_last_updated, updated_at)
        self.assertEqual(_run(image_entity.async_image()), b"png")

    def test_image_cache_key_removes_signed_query(self) -> None:
        """Image cache keys ignore temporary S3 query credentials."""

        cache_key = self.image_store.image_cache_key(
            "https://example.test/model.png?X-Amz-Security-Token=secret"
        )

        self.assertEqual(cache_key, "https://example.test/model.png")


if __name__ == "__main__":
    unittest.main()
