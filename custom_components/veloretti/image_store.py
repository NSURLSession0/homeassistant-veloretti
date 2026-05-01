"""Local vehicle image cache for the Veloretti integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class VelorettiCachedImage:
    """Metadata for one locally cached vehicle image."""

    public_path: str
    updated_at: datetime


class VelorettiVehicleImageStore:
    """Store Veloretti vehicle images in Home Assistant's public local folder."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create an image store rooted in ``/config/www/veloretti``."""

        self._hass = hass
        self._directory = Path(hass.config.path("www", "veloretti"))

    def public_path(self, vehicle_uuid: str) -> str:
        """Return the Home Assistant frontend path for a vehicle image."""

        return f"/local/veloretti/{_safe_filename(vehicle_uuid)}.png"

    async def async_exists(self, vehicle_uuid: str) -> bool:
        """Return whether the cached vehicle image file already exists."""

        path = self._file_path(vehicle_uuid)
        return await self._hass.async_add_executor_job(path.is_file)

    async def async_read(self, vehicle_uuid: str) -> bytes | None:
        """Read a cached vehicle image from disk for the image entity."""

        path = self._file_path(vehicle_uuid)
        return await self._hass.async_add_executor_job(_read_image, path)

    async def async_metadata(self, vehicle_uuid: str) -> VelorettiCachedImage | None:
        """Return metadata for an existing cached image file."""

        path = self._file_path(vehicle_uuid)
        return await self._hass.async_add_executor_job(
            _image_metadata,
            path,
            self.public_path(vehicle_uuid),
        )

    async def async_store(
        self,
        vehicle_uuid: str,
        image_content: bytes,
    ) -> VelorettiCachedImage:
        """Write the vehicle image to disk and return its cache metadata."""

        path = self._file_path(vehicle_uuid)
        await self._hass.async_add_executor_job(_write_image, path, image_content)
        cached_image = await self.async_metadata(vehicle_uuid)
        if cached_image is None:
            # The write helper creates the file before returning. This guard keeps
            # the method total for Home Assistant while still surfacing the cache path.
            return VelorettiCachedImage(
                public_path=self.public_path(vehicle_uuid),
                updated_at=datetime.now(UTC),
            )

        return cached_image

    def _file_path(self, vehicle_uuid: str) -> Path:
        """Return the local cache path for one vehicle image."""

        return self._directory / f"{_safe_filename(vehicle_uuid)}.png"


def image_cache_key(image_url: str) -> str:
    """Return the stable part of a signed image URL.

    Veloretti rotates the S3 query signature for the same image. Keeping only
    scheme, host and path lets the coordinator detect real model image changes
    without storing or comparing temporary credentials.
    """

    parsed_url = urlsplit(image_url)
    return urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            "",
            "",
        )
    )


def _safe_filename(value: str) -> str:
    """Return a filesystem-safe filename segment for API-provided identifiers."""

    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _read_image(path: Path) -> bytes | None:
    """Return cached image bytes when the file exists."""

    if not path.is_file():
        return None

    return path.read_bytes()


def _image_metadata(path: Path, public_path: str) -> VelorettiCachedImage | None:
    """Return cache metadata based on the local image file modification time."""

    if not path.is_file():
        return None

    return VelorettiCachedImage(
        public_path=public_path,
        updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
    )


def _write_image(path: Path, image_content: bytes) -> None:
    """Create the image directory and write one PNG cache file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_content)
