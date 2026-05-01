"""Async client for the Veloretti customer API."""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import time
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    API_BASE_URL,
    API_KEY,
    TOKEN_REFRESH_MARGIN_SECONDS,
    USER_AGENT,
    USER_TYPE,
)


class VelorettiError(Exception):
    """Base exception for Veloretti API failures."""


class VelorettiAuthError(VelorettiError):
    """Raised when the stored Veloretti credentials cannot authenticate."""


class VelorettiApiError(VelorettiError):
    """Raised when Veloretti returns an unexpected API response."""


@dataclass(slots=True)
class VelorettiTokens:
    """Current tokens returned by Veloretti.

    The access token is short-lived and authorizes vehicle data calls. The
    refresh token is long-lived and authorizes the dedicated refresh endpoint.
    """

    token: str
    refresh_token: str
    session_uuid: str | None = None


TokenUpdateCallback = Callable[[VelorettiTokens], Awaitable[None]]


def jwt_expiration(token: str) -> int | None:
    """Return the UNIX expiration timestamp embedded in a JWT without verifying it.

    Veloretti uses JWTs for both access and refresh tokens. The integration only
    reads the public payload so it can refresh before the short-lived access
    token expires; signature validation remains the API server's responsibility.
    """

    try:
        payload = token.split(".")[1]
        padded_payload = payload + "=" * (-len(payload) % 4)
        decoded_payload = base64.urlsafe_b64decode(padded_payload)
        value = json.loads(decoded_payload).get("exp")
    except (IndexError, ValueError, json.JSONDecodeError, TypeError):
        return None

    return int(value) if isinstance(value, int) else None


def parse_unix_timestamp(value: Any) -> datetime | None:
    """Convert Veloretti UNIX timestamps to timezone-aware datetimes."""

    if not isinstance(value, int | float):
        return None

    return datetime.fromtimestamp(value, tz=UTC)


def parse_iso_datetime(value: Any) -> datetime | None:
    """Convert Veloretti ISO datetimes to timezone-aware datetimes."""

    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class VelorettiClient:
    """Small async wrapper around the Veloretti customer API."""

    def __init__(
        self,
        session: ClientSession,
        *,
        token: str | None = None,
        refresh_token: str | None = None,
        session_uuid: str | None = None,
        on_tokens_updated: TokenUpdateCallback | None = None,
    ) -> None:
        """Create a client that stores token state in memory.

        Home Assistant persists token updates through ``on_tokens_updated`` so a
        refresh survives restarts without exposing the tokens as entities.
        """

        self._session = session
        self._token = token
        self._refresh_token = refresh_token
        self._session_uuid = session_uuid
        self._on_tokens_updated = on_tokens_updated

    @property
    def token(self) -> str | None:
        """Return the current short-lived access token."""

        return self._token

    @property
    def refresh_token(self) -> str | None:
        """Return the current long-lived refresh token."""

        return self._refresh_token

    async def request_magic_code(self, email: str) -> None:
        """Ask Veloretti to send a login code to the given email address."""

        await self._request(
            "GET",
            "/auth/magic/email",
            params={"email": email, "_": self._cache_buster()},
            authorize=False,
        )

    async def exchange_magic_code(self, email: str, code: str) -> VelorettiTokens:
        """Exchange the emailed login code for access and refresh tokens."""

        payload = await self._request(
            "POST",
            "/auth/magic/email",
            data={"email": email, "code": code},
            authorize=False,
        )
        tokens = self._tokens_from_payload(payload)
        await self._store_tokens(tokens)
        return tokens

    async def get_account(self) -> dict[str, Any]:
        """Return account data and the vehicle overview from Veloretti."""

        payload = await self._authorized_request("GET", "/auth")
        data = self._data_object(payload)

        # The auth endpoint returns freshly issued tokens together with account
        # data, so persisting them keeps the next poll inside Veloretti's short
        # access-token window.
        if "token" in data and "refresh_token" in data:
            await self._store_tokens(self._tokens_from_data(data))

        return data

    async def get_vehicle(self, vehicle_uuid: str) -> dict[str, Any]:
        """Return detail data for one vehicle."""

        payload = await self._authorized_request(
            "GET",
            f"/vehicles/{vehicle_uuid}",
            params={"_": self._cache_buster()},
        )
        return self._data_object(payload)

    async def download_vehicle_image(self, image_url: str) -> bytes:
        """Download a vehicle model image from Veloretti's signed image URL.

        Veloretti returns a short-lived S3 URL inside the authenticated vehicle
        payload. The URL itself authorizes the image request, so this method does
        not attach the Veloretti bearer token or API key.
        """

        try:
            response = await self._session.request(
                "GET",
                image_url,
                headers={
                    "Accept": "image/*",
                    "User-Agent": USER_AGENT,
                },
            )
        except ClientError as err:
            raise VelorettiApiError(
                "Could not download Veloretti vehicle image"
            ) from err

        async with response:
            if response.status >= 400:
                raise VelorettiApiError("Veloretti vehicle image download failed")

            image_content = await response.read()
            content_type = response.headers.get("Content-Type", "")
            if not content_type.lower().startswith("image/") and not _looks_like_image(
                image_content
            ):
                raise VelorettiApiError("Veloretti vehicle image was not an image")

            return image_content

    async def refresh_access_token(self) -> VelorettiTokens:
        """Use the refresh token to get a new access token."""

        if not self._refresh_token:
            raise VelorettiAuthError("No Veloretti refresh token is available")

        payload = await self._request(
            "GET",
            "/auth/refresh",
            bearer_token=self._refresh_token,
            retry_on_expired=False,
        )
        tokens = self._tokens_from_payload(payload)
        await self._store_tokens(tokens)
        return tokens

    async def _authorized_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a data request with refresh-before-use and one expired-token retry."""

        await self._refresh_if_needed()

        try:
            return await self._request(method, path, **kwargs)
        except VelorettiAuthError:
            await self.refresh_access_token()
            return await self._request(method, path, **kwargs)

    async def _refresh_if_needed(self) -> None:
        """Refresh the access token when the JWT is close to expiring."""

        if not self._token:
            raise VelorettiAuthError("No Veloretti access token is available")

        expires_at = jwt_expiration(self._token)
        if expires_at is None:
            return

        if expires_at - TOKEN_REFRESH_MARGIN_SECONDS <= int(time.time()):
            await self.refresh_access_token()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authorize: bool = True,
        bearer_token: str | None = None,
        retry_on_expired: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send one request and normalize Veloretti's JSON envelope."""

        headers = self._headers()
        selected_bearer_token = bearer_token or (self._token if authorize else None)
        if selected_bearer_token:
            headers["Authorization"] = f"Bearer {selected_bearer_token}"

        try:
            response = await self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                headers=headers,
                **kwargs,
            )
        except ClientError as err:
            raise VelorettiApiError("Could not reach Veloretti") from err

        async with response:
            payload = await self._json_response(response)

        message = str(payload.get("message", ""))
        if response.status == 498 and retry_on_expired and message == "Token expired":
            raise VelorettiAuthError("Veloretti access token expired")

        if response.status in (401, 403, 498):
            raise VelorettiAuthError(message or "Veloretti authentication failed")

        if response.status >= 400:
            raise VelorettiApiError(message or f"Veloretti returned {response.status}")

        return payload

    async def _json_response(self, response: ClientResponse) -> dict[str, Any]:
        """Read Veloretti's JSON response body and reject malformed payloads."""

        try:
            payload = await response.json(content_type=None)
        except (ClientError, ValueError, json.JSONDecodeError) as err:
            raise VelorettiApiError("Veloretti returned invalid JSON") from err

        if not isinstance(payload, dict):
            raise VelorettiApiError("Veloretti returned an unexpected JSON shape")

        return payload

    def _headers(self) -> dict[str, str]:
        """Return the static headers expected by the Veloretti customer API."""

        return {
            "Accept": "*/*",
            "User-Agent": USER_AGENT,
            "X-Api-Key": API_KEY,
            "X-User-Type": USER_TYPE,
        }

    def _tokens_from_payload(self, payload: dict[str, Any]) -> VelorettiTokens:
        """Extract token fields from Veloretti's standard response envelope."""

        return self._tokens_from_data(self._data_object(payload))

    def _tokens_from_data(self, data: dict[str, Any]) -> VelorettiTokens:
        """Build a token object from a Veloretti data object."""

        token = data.get("token")
        refresh_token = data.get("refresh_token")
        if not isinstance(token, str) or not isinstance(refresh_token, str):
            raise VelorettiAuthError("Veloretti did not return valid tokens")

        session_uuid = data.get("session_uuid")
        return VelorettiTokens(
            token=token,
            refresh_token=refresh_token,
            session_uuid=session_uuid if isinstance(session_uuid, str) else None,
        )

    def _data_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the ``data`` object from Veloretti's response envelope."""

        data = payload.get("data")
        if not isinstance(data, dict):
            raise VelorettiApiError("Veloretti did not return an object")

        return data

    async def _store_tokens(self, tokens: VelorettiTokens) -> None:
        """Update in-memory tokens and persist them through Home Assistant."""

        self._token = tokens.token
        self._refresh_token = tokens.refresh_token
        self._session_uuid = tokens.session_uuid

        if self._on_tokens_updated:
            await self._on_tokens_updated(tokens)

    def _cache_buster(self) -> str:
        """Return the millisecond cache-buster used by the official app."""

        return str(int(time.time() * 1000))


def _looks_like_image(content: bytes) -> bool:
    """Return whether bytes start with a known image file signature."""

    return content.startswith(
        (
            b"\x89PNG",
            b"\xff\xd8\xff",
            b"GIF8",
            b"RIFF",
        )
    )
