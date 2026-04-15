from __future__ import annotations

import pytest

from chift_cli import config
from chift_cli.client import apply_fields, apply_filter, build_request
from chift_cli.errors import ChiftCliError
from chift_cli.schema import Operation


OPERATION = Operation(
    vertical="consumers",
    entity="consumers",
    command="get",
    method="GET",
    path="/consumers/{consumer_id}",
    operation_id="consumers_get_consumer",
    summary="Get one consumer",
    scopes=(),
    raw={},
)


def test_build_request_uses_path_and_query_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "api_base_url", "https://example.test")
    request = build_request(OPERATION, params=["consumer_id=abc", "search=acme"], body=None)
    assert request["url"] == "https://example.test/consumers/abc"
    assert request["params"] == {"search": "acme"}


def test_build_request_requires_path_params() -> None:
    with pytest.raises(ChiftCliError) as exc_info:
        build_request(OPERATION, params=None, body=None)
    assert exc_info.value.message == "Missing path parameter `consumer_id`. Pass it with `--param consumer_id=...`."


def test_apply_fields_supports_nested_fields() -> None:
    data = {"id": "1", "nested": {"name": "Acme", "ignored": True}}
    assert apply_fields(data, "id,nested.name") == {"id": "1", "nested.name": "Acme"}


def test_apply_filter_keeps_matching_items() -> None:
    data = [{"name": "Acme"}, {"name": "Other"}]
    assert apply_filter(data, ["name=Acme"]) == [{"name": "Acme"}]
