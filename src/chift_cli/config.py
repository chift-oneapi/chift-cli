from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


APP_NAME = "chift-cli"
DEFAULT_API_BASE_URL = "https://api.chift.eu"
DEFAULT_OPENAPI_PATH = "/openapi.json"
DEFAULT_SCHEMA_REFRESH_INTERVAL_SECONDS = 7 * 24 * 60 * 60
INTERNAL_ENDPOINT_VERTICALS = {
    "datastores",
    "general",
    "issues",
    "syncs",
    "m-c-p",
    "webhooks",
}
PLATFORM_CONFIG_VERTICALS = {"consumers", "integrations"}


class ChiftSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHIFT_", extra="ignore")

    api_base_url: str = DEFAULT_API_BASE_URL
    openapi_path: str = DEFAULT_OPENAPI_PATH
    openapi_url: str | None = None

    @model_validator(mode="after")
    def derive_openapi_url(self) -> "ChiftSettings":
        if self.openapi_url and self.openapi_url.startswith("http"):
            return self
        path = self.openapi_url or self.openapi_path
        if not path.startswith("/"):
            path = f"/{path}"
        self.openapi_url = f"{self.api_base_url.rstrip('/')}{path}"
        return self

    config_dir: str | None = None
    cache_dir: str | None = None
    show_internal_endpoints: bool = False
    show_platform_endpoints: bool = False
    allowed_operations: str | None = None
    consumer_id: str | None = None
    schema_refresh_interval_seconds: int = DEFAULT_SCHEMA_REFRESH_INTERVAL_SECONDS


settings = ChiftSettings()  # type: ignore[reportCallIssue]


@dataclass
class ApiKeyCredentials:
    client_id: str
    client_secret: str
    account_id: str = ""
    consumer_id: str | None = None


@dataclass
class Token:
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800
    expires_on: int | None = None


def config_dir() -> Path:
    root = settings.config_dir or os.environ.get("XDG_CONFIG_HOME")
    return Path(root, APP_NAME) if root else Path.home() / ".config" / APP_NAME


def cache_dir() -> Path:
    root = settings.cache_dir or os.environ.get("XDG_CACHE_HOME")
    return Path(root, APP_NAME) if root else Path.home() / ".cache" / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def schema_path() -> Path:
    return cache_dir() / "openapi.json"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_api_base_url(config: dict[str, Any] | None = None) -> str:
    data = config if config is not None else load_config()
    configured = settings.api_base_url
    return (
        configured
        if "api_base_url" in settings.model_fields_set
        else data.get("api_base_url") or configured
    )


def get_openapi_url(config: dict[str, Any] | None = None) -> str:
    data = config if config is not None else load_config()
    configured = settings.openapi_url
    if not configured:
        raise ValueError("OpenAPI URL is not set")
    return (
        configured
        if {"api_base_url", "openapi_path", "openapi_url"} & settings.model_fields_set
        else data.get("openapi_url") or configured
    )


def show_internal_endpoints() -> bool:
    return settings.show_internal_endpoints


def show_platform_endpoints() -> bool:
    return settings.show_platform_endpoints


def endpoint_visible(vertical: str) -> bool:
    if vertical in INTERNAL_ENDPOINT_VERTICALS:
        return show_internal_endpoints()
    if vertical in PLATFORM_CONFIG_VERTICALS:
        return show_platform_endpoints()
    return True


def save_api_key_credentials(credentials: ApiKeyCredentials) -> None:
    data = load_config()
    data["api_key"] = asdict(credentials)
    save_config(data)


def load_api_key_credentials() -> ApiKeyCredentials | None:
    data = load_config().get("api_key")
    if not data:
        return None
    return ApiKeyCredentials(**data)


def save_token(token: Token) -> None:
    data = load_config()
    data["token"] = asdict(token)
    save_config(data)


def load_token() -> Token | None:
    data = load_config().get("token")
    if not data:
        return None
    return Token(**data)
