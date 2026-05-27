from __future__ import annotations

import pytest

from chift_cli import config
from chift_cli.cli import _input_values_from_args
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


def test_apply_fields_keeps_explicit_none_values() -> None:
    data = {"id": "1", "deleted_at": None}
    assert apply_fields(data, "id,deleted_at,missing") == {
        "id": "1",
        "deleted_at": None,
    }


def test_apply_filter_keeps_matching_items() -> None:
    data = [{"name": "Acme"}, {"name": "Other"}]
    assert apply_filter(data, ["name=Acme"]) == [{"name": "Acme"}]


def test_apply_filter_handles_paginated_envelope() -> None:
    data = {
        "items": [{"name": "Acme"}, {"name": "Other"}],
        "page": 1,
        "size": 50,
        "total": 2,
    }
    assert apply_filter(data, ["name=Acme"]) == {
        "items": [{"name": "Acme"}],
        "page": 1,
        "size": 50,
        "total": 1,
    }


def test_apply_fields_handles_paginated_envelope() -> None:
    data = {
        "items": [{"id": "1", "name": "Acme", "extra": True}],
        "page": 1,
        "size": 50,
        "total": 1,
    }
    assert apply_fields(data, "id,name") == {
        "items": [{"id": "1", "name": "Acme"}],
        "page": 1,
        "size": 50,
        "total": 1,
    }


def test_apply_fields_supports_array_indices() -> None:
    data = {
        "id": "1",
        "addresses": [{"country": "BE"}, {"country": "FR"}],
    }
    assert apply_fields(data, "id,addresses.0.country,addresses.1.country") == {
        "id": "1",
        "addresses.0.country": "BE",
        "addresses.1.country": "FR",
    }


def test_apply_filter_normalizes_booleans_and_null() -> None:
    data = {
        "items": [
            {"name": "Alpha", "is_company": True, "parent": None},
            {"name": "Bravo", "is_company": False, "parent": "x"},
        ],
        "page": 1,
        "size": 50,
        "total": 2,
    }
    only_companies = apply_filter(data, ["is_company=true"])
    assert [item["name"] for item in only_companies["items"]] == ["Alpha"]

    only_root = apply_filter(data, ["parent=null"])
    assert [item["name"] for item in only_root["items"]] == ["Alpha"]


def test_build_request_coerces_input_values_for_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "api_base_url", "https://example.test")
    op = Operation(
        vertical="accounting",
        entity="suppliers",
        command="create",
        method="POST",
        path="/consumers/{consumer_id}/accounting/suppliers",
        operation_id="",
        summary="",
        scopes=(),
        raw={
            "parameters": [
                {
                    "name": "consumer_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
        },
    )
    request = build_request(
        op,
        params=None,
        body=None,
        input_values={
            "consumer_id": "c1",
            "name": "Acme",
            "addresses": '[{"country":"BE"}]',
            "active": "true",
        },
    )
    assert request["json"] == {
        "name": "Acme",
        "addresses": [{"country": "BE"}],
        "active": True,
    }


def test_positional_key_value_inputs_coerce_like_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "api_base_url", "https://example.test")
    op = Operation(
        vertical="accounting",
        entity="suppliers",
        command="create",
        method="POST",
        path="/consumers/{consumer_id}/accounting/suppliers",
        operation_id="",
        summary="",
        scopes=(),
        raw={
            "parameters": [
                {
                    "name": "consumer_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
        },
    )
    input_values = _input_values_from_args(op, ["c1", "active=true", 'addresses=[{"country":"BE"}]'], None)
    request = build_request(op, params=None, body=None, input_values=input_values)
    assert request["json"] == {
        "addresses": [{"country": "BE"}],
        "active": True,
    }


def test_build_request_coerces_json_param_values_for_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "api_base_url", "https://example.test")
    op = Operation(
        vertical="accounting",
        entity="suppliers",
        command="create",
        method="POST",
        path="/consumers/{consumer_id}/accounting/suppliers",
        operation_id="",
        summary="",
        scopes=(),
        raw={
            "parameters": [
                {
                    "name": "consumer_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
        },
    )
    request = build_request(
        op,
        params=[
            "consumer_id=c1",
            "name=Acme",
            'addresses=[{"country":"BE"}]',
            "active=true",
        ],
        body=None,
    )
    assert request["json"] == {
        "name": "Acme",
        "addresses": [{"country": "BE"}],
        "active": True,
    }


def test_build_request_rejects_body_inputs_when_json_body_is_not_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "api_base_url", "https://example.test")
    op = Operation(
        vertical="accounting",
        entity="clients",
        command="create",
        method="POST",
        path="/consumers/{consumer_id}/accounting/clients",
        operation_id="",
        summary="",
        scopes=(),
        raw={
            "parameters": [
                {
                    "name": "consumer_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
        },
    )
    with pytest.raises(ChiftCliError) as exc_info:
        from chift_cli.client import build_request as br

        br(op, params=["consumer_id=c1"], body="[1,2,3]", input_values={"name": "x"})
    assert "non-object --json body" in exc_info.value.message
