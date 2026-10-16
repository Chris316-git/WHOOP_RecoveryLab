"""WHOOP OAuth 2.0 helpers: authorization URL, code exchange, token refresh."""
import secrets
from urllib.parse import urlencode

import httpx

from src import config
from src.ingestion.token_store import WhoopToken


def _client_credentials() -> dict:
    return {
        "client_id": config.require("WHOOP_CLIENT_ID"),
        "client_secret": config.require("WHOOP_CLIENT_SECRET"),
    }


def new_state() -> str:
    # WHOOP requires a state value of at least 8 characters.
    return secrets.token_urlsafe(16)


def build_authorization_url(state: str) -> str:
    params = {
        "client_id": config.require("WHOOP_CLIENT_ID"),
        "redirect_uri": config.WHOOP_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(config.WHOOP_SCOPES),
        "state": state,
    }
    return f"{config.WHOOP_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> WhoopToken:
    response = httpx.post(
        config.WHOOP_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.WHOOP_REDIRECT_URI,
            **_client_credentials(),
        },
        timeout=30,
    )
    response.raise_for_status()
    return WhoopToken.from_response(response.json())


def refresh(token: WhoopToken) -> WhoopToken:
    """Refreshing returns a NEW refresh token and invalidates the old one, so always save the result."""
    response = httpx.post(
        config.WHOOP_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "scope": "offline",
            **_client_credentials(),
        },
        timeout=30,
    )
    response.raise_for_status()
    return WhoopToken.from_response(response.json())
