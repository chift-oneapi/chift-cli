from __future__ import annotations

from chift_cli import config


def test_internal_endpoints_hidden_by_default(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "show_internal_endpoints", False)

    assert not config.endpoint_visible("general")
    assert not config.endpoint_visible("datastores")
    assert not config.endpoint_visible("syncs")
    assert not config.endpoint_visible("issues")


def test_platform_endpoints_hidden_by_default(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "show_platform_endpoints", False)

    assert not config.endpoint_visible("consumers")
    assert not config.endpoint_visible("integrations")


def test_feature_flags_enable_hidden_endpoint_groups(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "show_internal_endpoints", True)
    monkeypatch.setattr(config.settings, "show_platform_endpoints", True)

    assert config.endpoint_visible("general")
    assert config.endpoint_visible("datastores")
    assert config.endpoint_visible("syncs")
    assert config.endpoint_visible("issues")
    assert config.endpoint_visible("consumers")
    assert config.endpoint_visible("integrations")


def test_normal_verticals_are_visible_without_flags(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "show_internal_endpoints", False)
    monkeypatch.setattr(config.settings, "show_platform_endpoints", False)

    assert config.endpoint_visible("accounting")
    assert config.endpoint_visible("banking")
    assert config.endpoint_visible("point-of-sale")


def test_settings_derive_openapi_url_from_default_base(monkeypatch) -> None:
    monkeypatch.delenv("CHIFT_API_BASE_URL", raising=False)
    monkeypatch.delenv("CHIFT_OPENAPI_URL", raising=False)
    monkeypatch.delenv("CHIFT_OPENAPI_PATH", raising=False)

    settings = config.ChiftSettings()

    assert settings.api_base_url == "https://api.chift.eu"
    assert settings.openapi_url == "https://api.chift.eu/openapi.json"


def test_settings_derive_openapi_url_from_api_base_url(monkeypatch) -> None:
    monkeypatch.setenv("CHIFT_API_BASE_URL", "http://chift.localhost:8000")
    monkeypatch.delenv("CHIFT_OPENAPI_URL", raising=False)
    monkeypatch.delenv("CHIFT_OPENAPI_PATH", raising=False)

    settings = config.ChiftSettings()

    assert settings.api_base_url == "http://chift.localhost:8000"
    assert settings.openapi_url == "http://chift.localhost:8000/openapi.json"


def test_settings_reads_allowed_operations_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CHIFT_ALLOWED_OPERATIONS", "get,post")

    settings = config.ChiftSettings()

    assert settings.allowed_operations == "get,post"


def test_settings_reads_platform_visibility_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CHIFT_SHOW_PLATFORM_ENDPOINTS", "1")

    settings = config.ChiftSettings()

    assert settings.show_platform_endpoints is True


def test_settings_default_schema_refresh_interval_is_one_week(monkeypatch) -> None:
    monkeypatch.delenv("CHIFT_SCHEMA_REFRESH_INTERVAL_SECONDS", raising=False)

    settings = config.ChiftSettings()

    assert settings.schema_refresh_interval_seconds == 7 * 24 * 60 * 60


def test_settings_reads_schema_refresh_interval_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CHIFT_SCHEMA_REFRESH_INTERVAL_SECONDS", "3600")

    settings = config.ChiftSettings()

    assert settings.schema_refresh_interval_seconds == 3600
