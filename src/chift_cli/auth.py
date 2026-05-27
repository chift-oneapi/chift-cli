from __future__ import annotations

import time
from typing import Any

import httpx

from .config import (
    ApiKeyCredentials,
    Token,
    get_api_base_url,
    load_api_key_credentials,
    load_token,
    save_token,
)
from .errors import AuthenticationError, RetryRecommendedError
from .output import log

TOKEN_REFRESH_SKEW_SECONDS = 60


def _auth_payload(credentials: ApiKeyCredentials) -> dict[str, str]:
    return {
        "clientId": credentials.client_id,
        "clientSecret": credentials.client_secret,
        "accountId": credentials.account_id,
    }


def _message_from_payload(data: Any) -> str | None:
    if isinstance(data, str):
        return data.strip() or None
    if isinstance(data, list):
        messages = [_message_from_payload(item) for item in data]
        return "; ".join(message for message in messages if message) or None
    if not isinstance(data, dict):
        return None
    for key in ("detail", "reason", "msg", "error_description", "message", "error"):
        value = data.get(key)
        message = _message_from_payload(value)
        if message:
            return message
    return None


def _auth_error_message(response: httpx.Response) -> str:
    try:
        reason = _message_from_payload(response.json())
    except ValueError:
        reason = response.text.strip() or None
    if reason:
        return f"Could not authenticate with Chift. reason: {reason}"
    return f"Chift authentication failed with HTTP {response.status_code}."


def token_is_valid(token: Token | None) -> bool:
    if not token or not token.access_token:
        return False
    if token.expires_on is None:
        return False
    return token.expires_on - TOKEN_REFRESH_SKEW_SECONDS > int(time.time())


def fetch_token(credentials: ApiKeyCredentials, *, timeout: float = 20.0, debug: bool = False) -> Token:
    url = f"{get_api_base_url().rstrip('/')}/token"
    payload = _auth_payload(credentials)
    log(f"POST {url}", debug=debug)
    try:
        response = httpx.post(url, json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        raise RetryRecommendedError("Could not reach Chift token endpoint.", details={"reason": str(exc)}) from exc
    if response.status_code in {401, 403}:
        raise AuthenticationError(
            _auth_error_message(response),
            details={"status_code": response.status_code, "body": response.text},
        )
    if response.status_code >= 500:
        raise RetryRecommendedError(
            _auth_error_message(response),
            details={"status_code": response.status_code, "body": response.text},
        )
    if response.status_code >= 400:
        raise AuthenticationError(
            _auth_error_message(response),
            details={"status_code": response.status_code, "body": response.text},
        )
    data: dict[str, Any] = response.json()
    token = Token(
        access_token=data["access_token"],
        token_type=data.get("token_type", "bearer"),
        expires_in=int(data.get("expires_in", 1800)),
        expires_on=int(data.get("expires_on") or (time.time() + int(data.get("expires_in", 1800)))),
    )
    save_token(token)
    return token


def get_access_token(*, debug: bool = False) -> str:
    token = load_token()
    if token and token_is_valid(token):
        return token.access_token
    credentials = load_api_key_credentials()
    if not credentials:
        raise AuthenticationError("No API credentials found. Run `chift auth setup` first.")
    return fetch_token(credentials, debug=debug).access_token
