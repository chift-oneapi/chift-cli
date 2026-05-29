import os


def pytest_configure(config) -> None:
    # The CLI command tree is built at chift_cli.cli import time, which
    # happens during test collection. Set the platform-endpoints flag now
    # so dynamic commands like `consumers` are registered for the tests
    # that exercise them. Per-test overrides go through monkeypatch.setattr.
    os.environ.setdefault("CHIFT_SHOW_PLATFORM_ENDPOINTS", "1")
