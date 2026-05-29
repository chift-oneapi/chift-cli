import os
import shutil
import tempfile
from pathlib import Path

FIXTURE_SCHEMA = Path(__file__).parent / "fixtures" / "openapi.json"


def pytest_configure(config) -> None:
    # The CLI command tree is built at chift_cli.cli import time, which happens
    # during test collection. Two env vars must be set before that import:
    #
    #   CHIFT_SHOW_PLATFORM_ENDPOINTS=1  registers dynamic commands like
    #       `consumers` so the tests that exercise them can find the operations.
    #
    #   CHIFT_CACHE_DIR points the schema cache at a copy of the committed
    #       fixture, so building the tree never reaches the live OpenAPI
    #       endpoint over the network. We copy into a temp dir (rather than
    #       pointing at the repo) so a background refresh can't write into the
    #       source tree.
    #
    # Per-test overrides go through monkeypatch.setattr on config.settings.
    os.environ.setdefault("CHIFT_SHOW_PLATFORM_ENDPOINTS", "1")

    cache_dir = Path(tempfile.mkdtemp(prefix="chift-cli-test-cache-"))
    shutil.copyfile(FIXTURE_SCHEMA, cache_dir / "openapi.json")
    os.environ.setdefault("CHIFT_CACHE_DIR", str(cache_dir))
    # Disable the stale-cache background refresh so import never fetches live.
    os.environ.setdefault("CHIFT_SCHEMA_REFRESH_INTERVAL_SECONDS", "0")
    config._chift_cli_test_cache_dir = cache_dir


def pytest_unconfigure(config) -> None:
    cache_dir = getattr(config, "_chift_cli_test_cache_dir", None)
    if cache_dir is not None:
        shutil.rmtree(cache_dir, ignore_errors=True)
