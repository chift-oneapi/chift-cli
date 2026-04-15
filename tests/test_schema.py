from __future__ import annotations

import httpx

from chift_cli import config
from chift_cli.schema import find_operation, load_schema, response_is_collection, search_schema, schema_path, tree


SAMPLE_SCHEMA = {
    "components": {
        "schemas": {
            "Account": {"type": "object", "properties": {"id": {"type": "string"}}},
            "AccountBalance": {"type": "object", "properties": {"id": {"type": "string"}}},
            "ChiftPage_AccountBalance_": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"$ref": "#/components/schemas/AccountBalance"}},
                    "page": {"type": "integer"},
                    "size": {"type": "integer"},
                    "total": {"type": "integer"},
                },
                "required": ["items", "total", "page", "size"],
            },
        }
    },
    "paths": {
        "/consumers": {
            "get": {
                "tags": ["Consumers"],
                "summary": "Get consumers",
                "operationId": "consumers_get_consumers",
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}},
            },
            "post": {
                "tags": ["Consumers"],
                "summary": "Create new consumer",
                "operationId": "consumers_create_consumer",
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            },
        },
        "/consumers/{consumer_id}": {
            "get": {
                "tags": ["Consumers"],
                "summary": "Get one consumer",
                "operationId": "consumers_get_consumer",
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            },
            "delete": {
                "tags": ["Consumers"],
                "summary": "Delete one consumer",
                "operationId": "consumers_delete_consumer",
            },
        },
        "/consumers/{consumer_id}/accounting/journal_entries": {
            "get": {
                "tags": ["Accounting"],
                "summary": "Get journal entries",
                "operationId": "accounting_get_journal_entries",
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}},
            }
        },
        "/consumers/{consumer_id}/accounting/accounts/search": {
            "post": {
                "tags": ["Accounting"],
                "summary": "Search accounts",
                "operationId": "accounting_search_accounts",
                "security": [{"mcp_auth": ["accounting.accounts.read"]}],
                "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Account"}}}}},
            }
        },
        "/consumers/{consumer_id}/accounting/accounts": {
            "post": {
                "tags": ["Accounting"],
                "summary": "Create account",
                "operationId": "accounting_create_account",
                "security": [{"mcp_auth": ["accounting.accounts.write"]}],
                "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Account"}}}}},
            }
        },
        "/consumers/{consumer_id}/accounting/chart-of-accounts/balance": {
            "post": {
                "tags": ["Accounting"],
                "summary": "Get accounts balances",
                "operationId": "accounting_get_accounts_balances",
                "security": [{"mcp_auth": ["accounting.ledger_accounts.read"]}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ChiftPage_AccountBalance_"}}}}
                },
            }
        },
    }
}


def test_builds_tree_from_openapi_paths() -> None:
    result = tree(SAMPLE_SCHEMA)
    assert "consumers" in result
    assert "consumers" in result["consumers"]
    assert {item["command"] for item in result["consumers"]["consumers"]} == {"list", "create", "get", "delete"}
    assert result["accounting"]["journal-entries"][0]["method"] == "GET"
    assert {item["command"] for item in result["accounting"]["accounts"]} == {"get", "create"}
    assert result["accounting"]["ledger-accounts"][0]["command"] == "list"


def test_find_operation() -> None:
    operation = find_operation("consumers", "consumers", "get", SAMPLE_SCHEMA)
    assert operation is not None
    assert operation.path == "/consumers/{consumer_id}"


def test_search_schema_matches_fields() -> None:
    result = search_schema("journal", SAMPLE_SCHEMA)
    assert result[0]["vertical"] == "accounting"
    assert result[0]["entity"] == "journal-entries"


def test_operations_store_scopes() -> None:
    operation = find_operation("accounting", "accounts", "get", SAMPLE_SCHEMA)
    assert operation is not None
    assert operation.scopes == ("accounting.accounts.read",)


def test_response_is_collection_detects_arrays_and_chift_pages() -> None:
    array_operation = SAMPLE_SCHEMA["paths"]["/consumers"]["get"]
    page_operation = SAMPLE_SCHEMA["paths"]["/consumers/{consumer_id}/accounting/chart-of-accounts/balance"]["post"]
    single_operation = SAMPLE_SCHEMA["paths"]["/consumers/{consumer_id}/accounting/accounts/search"]["post"]

    assert response_is_collection(array_operation, SAMPLE_SCHEMA)
    assert response_is_collection(page_operation, SAMPLE_SCHEMA)
    assert not response_is_collection(single_operation, SAMPLE_SCHEMA)


def test_load_schema_fetches_openapi_when_cache_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "openapi_url", "https://example.test/openapi.json")

    def fake_get(url: str, *, timeout: float):
        assert url == "https://example.test/openapi.json"
        assert timeout == 30.0
        return httpx.Response(200, json=SAMPLE_SCHEMA, request=httpx.Request("GET", url))

    monkeypatch.setattr("chift_cli.schema.httpx.get", fake_get)

    assert load_schema() == SAMPLE_SCHEMA
    assert schema_path().exists()
