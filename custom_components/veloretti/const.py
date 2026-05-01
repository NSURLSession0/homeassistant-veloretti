"""Constants for the Veloretti integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "veloretti"

API_BASE_URL = "https://customer-api.veloretti-backoffice.com/v3"
API_KEY = "8d5909b6-8850-4e19-8ec9-443a3b94a1cd"
USER_TYPE = "shopify"
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)

CONF_ACCOUNT_UUID = "account_uuid"
CONF_EMAIL = "email"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
CONF_SESSION_UUID = "session_uuid"
CONF_TOKEN = "token"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
DEFAULT_SCAN_INTERVAL_MINUTES = 5
IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 10
SCAN_INTERVAL_MINUTE_OPTIONS = (5, 10, 15, 30)
TOKEN_REFRESH_MARGIN_SECONDS = 60
