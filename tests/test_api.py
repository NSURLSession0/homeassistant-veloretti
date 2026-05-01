"""Fast unit tests for Veloretti token handling."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import importlib.util
import json
from pathlib import Path
import sys
import time
import types
import unittest
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _load_api_module() -> Any:
    """Load the API module without importing Home Assistant-only files."""

    aiohttp_module = types.ModuleType("aiohttp")
    aiohttp_module.ClientError = Exception
    aiohttp_module.ClientResponse = object
    aiohttp_module.ClientSession = object
    sys.modules["aiohttp"] = aiohttp_module

    package = types.ModuleType("custom_components.veloretti")
    package.__path__ = [str(ROOT / "custom_components" / "veloretti")]
    sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
    sys.modules["custom_components.veloretti"] = package

    const_spec = importlib.util.spec_from_file_location(
        "custom_components.veloretti.const",
        ROOT / "custom_components" / "veloretti" / "const.py",
    )
    assert const_spec and const_spec.loader
    const_module = importlib.util.module_from_spec(const_spec)
    sys.modules["custom_components.veloretti.const"] = const_module
    const_spec.loader.exec_module(const_module)

    api_spec = importlib.util.spec_from_file_location(
        "custom_components.veloretti.api",
        ROOT / "custom_components" / "veloretti" / "api.py",
    )
    assert api_spec and api_spec.loader
    api_module = importlib.util.module_from_spec(api_spec)
    sys.modules["custom_components.veloretti.api"] = api_module
    api_spec.loader.exec_module(api_module)
    return api_module


api = _load_api_module()


class FakeResponse:
    """Minimal aiohttp-like response used by the client tests."""

    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        """Create a fake response with a status and JSON payload."""

        self.status = status
        self._payload = payload

    async def __aenter__(self) -> FakeResponse:
        """Enter the async context manager used by aiohttp responses."""

        return self

    async def __aexit__(self, *_args: object) -> None:
        """Exit the async context manager."""

    async def json(self, *, content_type: str | None = None) -> dict[str, Any]:
        """Return the configured JSON payload."""

        return self._payload


class FakeSession:
    """Minimal aiohttp-like session that returns queued responses."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        """Create a fake session with responses consumed in request order."""

        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        """Record the outgoing request and return the next fake response."""

        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def _token(expires_in: int, *, issued_at: int | None = None) -> str:
    """Create an unsigned JWT-shaped token for expiration tests."""

    issued_at = issued_at or int(time.time())
    payload = {"iat": issued_at, "exp": issued_at + expires_in}
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"header.{encoded_payload.rstrip('=')}.signature"


def _run(coro: Awaitable[Any]) -> Any:
    """Run an async client call from a synchronous pytest test."""

    return asyncio.run(coro)


class VelorettiApiTests(unittest.TestCase):
    """Unit tests for the dependency-light API client."""

    def test_jwt_expiration_reads_public_payload(self) -> None:
        """The client reads JWT expiration timestamps without validating secrets."""

        token = _token(300, issued_at=1000)

        self.assertEqual(api.jwt_expiration(token), 1300)

    def test_refresh_uses_refresh_token_before_data_request(self) -> None:
        """Expired access tokens are refreshed before vehicle data is requested."""

        stored_tokens: list[Any] = []
        refreshed_token = _token(300)
        refreshed_refresh_token = _token(315360000)
        session = FakeSession(
            [
                FakeResponse(
                    200,
                    {
                        "data": {
                            "token": refreshed_token,
                            "refresh_token": refreshed_refresh_token,
                            "session_uuid": "session",
                        }
                    },
                ),
                FakeResponse(200, {"data": {"uuid": "vehicle"}}),
            ]
        )

        async def store_tokens(tokens: Any) -> None:
            """Capture persisted tokens for assertions."""

            stored_tokens.append(tokens)

        client = api.VelorettiClient(
            session,
            token=_token(-60),
            refresh_token=_token(315360000),
            on_tokens_updated=store_tokens,
        )

        result = _run(client.get_vehicle("vehicle"))

        self.assertEqual(result, {"uuid": "vehicle"})
        self.assertTrue(session.calls[0]["url"].endswith("/auth/refresh"))
        self.assertTrue(
            session.calls[0]["headers"]["Authorization"].startswith("Bearer ")
        )
        self.assertEqual(
            session.calls[1]["headers"]["Authorization"],
            f"Bearer {refreshed_token}",
        )
        self.assertEqual(stored_tokens[-1].token, refreshed_token)

    def test_token_expired_response_refreshes_once_and_retries(self) -> None:
        """A 498 token-expired response refreshes once and retries the request."""

        refreshed_token = _token(300)
        session = FakeSession(
            [
                FakeResponse(498, {"message": "Token expired", "data": None}),
                FakeResponse(
                    200,
                    {
                        "data": {
                            "token": refreshed_token,
                            "refresh_token": _token(315360000),
                        }
                    },
                ),
                FakeResponse(200, {"data": {"uuid": "vehicle"}}),
            ]
        )
        client = api.VelorettiClient(
            session,
            token=_token(300),
            refresh_token=_token(315360000),
        )

        result = _run(client.get_vehicle("vehicle"))

        self.assertEqual(result, {"uuid": "vehicle"})
        self.assertTrue(session.calls[0]["url"].endswith("/vehicles/vehicle"))
        self.assertTrue(session.calls[1]["url"].endswith("/auth/refresh"))
        self.assertTrue(session.calls[2]["url"].endswith("/vehicles/vehicle"))

    def test_account_response_updates_tokens(self) -> None:
        """The auth overview persists the fresh tokens returned by Veloretti."""

        stored_tokens: list[Any] = []
        new_token = _token(300)
        new_refresh_token = _token(315360000)
        session = FakeSession(
            [
                FakeResponse(
                    200,
                    {
                        "data": {
                            "uuid": "account",
                            "vehicles": {},
                            "token": new_token,
                            "refresh_token": new_refresh_token,
                            "session_uuid": "session",
                        }
                    },
                )
            ]
        )

        async def store_tokens(tokens: Any) -> None:
            """Capture persisted tokens for assertions."""

            stored_tokens.append(tokens)

        client = api.VelorettiClient(
            session,
            token=_token(300),
            refresh_token=_token(315360000),
            on_tokens_updated=store_tokens,
        )

        account = _run(client.get_account())

        self.assertEqual(account["uuid"], "account")
        self.assertEqual(stored_tokens[-1].token, new_token)
        self.assertEqual(stored_tokens[-1].refresh_token, new_refresh_token)


if __name__ == "__main__":
    unittest.main()
