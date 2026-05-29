from pathlib import Path

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
    monkeypatch.setenv("CHIFT_ALLOWED_OPERATIONS", "read,write")

    settings = config.ChiftSettings()

    assert settings.allowed_operations == "read,write"


def test_settings_reads_platform_visibility_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CHIFT_SHOW_PLATFORM_ENDPOINTS", "1")

    settings = config.ChiftSettings()

    assert settings.show_platform_endpoints is True


# The per-platform default location is delegated to platformdirs (which has its
# own test suite). Here we only verify the override precedence we own: an
# explicit setting beats the XDG env var, which beats the platform default.


def test_config_dir_setting_overrides_xdg_and_platform_default(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "config_dir", "/custom/root")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/me/.config")

    assert config.config_dir() == Path("/custom/root", config.APP_NAME)


def test_config_dir_falls_back_to_xdg_env(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "config_dir", None)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/me/.config")

    assert config.config_dir() == Path("/home/me/.config", config.APP_NAME)


def test_config_dir_uses_platform_default_without_overrides(monkeypatch) -> None:
    from platformdirs import user_config_path

    monkeypatch.setattr(config.settings, "config_dir", None)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert config.config_dir() == user_config_path(config.APP_NAME, appauthor=False)


def test_cache_dir_setting_overrides_xdg_and_platform_default(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "cache_dir", "/custom/cache")
    monkeypatch.setenv("XDG_CACHE_HOME", "/home/me/.cache")

    assert config.cache_dir() == Path("/custom/cache", config.APP_NAME)


def test_cache_dir_falls_back_to_xdg_env(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "cache_dir", None)
    monkeypatch.setenv("XDG_CACHE_HOME", "/home/me/.cache")

    assert config.cache_dir() == Path("/home/me/.cache", config.APP_NAME)


def test_cache_dir_uses_platform_default_without_overrides(monkeypatch) -> None:
    from platformdirs import user_cache_path

    monkeypatch.setattr(config.settings, "cache_dir", None)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    assert config.cache_dir() == user_cache_path(config.APP_NAME, appauthor=False)
