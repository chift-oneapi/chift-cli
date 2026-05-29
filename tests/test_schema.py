import json
import os
import time

import httpx

from chift_cli import config
from chift_cli.schema import (
    find_operation,
    iter_operations,
    load_schema,
    response_is_collection,
    save_schema,
    schema_path,
    search_schema,
    tree,
)

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
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}
                },
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
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}
                },
            }
        },
        "/consumers/{consumer_id}/accounting/accounts/search": {
            "post": {
                "tags": ["Accounting"],
                "summary": "Search accounts",
                "operationId": "accounting_search_accounts",
                "security": [{"mcp_auth": ["accounting.accounts.read"]}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Account"}}}}
                },
            }
        },
        "/consumers/{consumer_id}/accounting/accounts": {
            "post": {
                "tags": ["Accounting"],
                "summary": "Create account",
                "operationId": "accounting_create_account",
                "security": [{"mcp_auth": ["accounting.accounts.write"]}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Account"}}}}
                },
            }
        },
        "/consumers/{consumer_id}/accounting/chart-of-accounts/balance": {
            "post": {
                "tags": ["Accounting"],
                "summary": "Get accounts balances",
                "operationId": "accounting_get_accounts_balances",
                "security": [{"mcp_auth": ["accounting.ledger_accounts.read"]}],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/ChiftPage_AccountBalance_"}}
                        }
                    }
                },
            }
        },
        "/consumers/{consumer_id}/accounting/tax-rates": {
            "get": {
                "tags": ["General"],
                "summary": "Get tax rates",
                "operationId": "generic_get_tax_rates",
                "security": [{"mcp_auth": ["accounting.tax_rates.read"]}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}
                },
            }
        },
        "/consumers/{consumer_id}/accounting/vat-codes": {
            "get": {
                "tags": ["Accounting", "Vat Codes"],
                "summary": "Get VAT codes",
                "operationId": "tagged_get_vat_codes",
                "security": [{"mcp_auth": ["banking.accounts.read"]}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}
                },
            }
        },
        "/consumers/{consumer_id}/payment/transactions": {
            "get": {
                "summary": "Get payment transactions",
                "operationId": "path_get_payment_transactions",
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}
                },
            }
        },
    },
}


def test_builds_tree_from_openapi_paths() -> None:
    result = tree(SAMPLE_SCHEMA)
    assert "consumers" in result
    assert "consumers" in result["consumers"]
    assert {item["command"] for item in result["consumers"]["consumers"]} == {"list", "create", "get", "delete"}
    assert result["accounting"]["journal-entries"][0]["method"] == "GET"
    assert {item["command"] for item in result["accounting"]["accounts"]} == {"get", "create"}
    assert result["accounting"]["ledger-accounts"][0]["command"] == "list"
    assert result["accounting"]["tax-rates"][0]["operation_id"] == "generic_get_tax_rates"
    assert result["banking"]["accounts"][0]["operation_id"] == "tagged_get_vat_codes"
    assert result["payment"]["transactions"][0]["operation_id"] == "path_get_payment_transactions"


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


def test_iter_operations_includes_head_and_options_methods() -> None:
    schema = {
        "paths": {
            "/consumers/{consumer_id}/accounting/status": {
                "head": {"tags": ["Accounting"]},
                "options": {"tags": ["Accounting"]},
            }
        }
    }

    methods = {operation.method for operation in iter_operations(schema)}

    assert methods == {"HEAD", "OPTIONS"}


def test_operation_classification_uses_scopes_when_two_tags_are_missing() -> None:
    operation = find_operation("accounting", "tax-rates", "list", SAMPLE_SCHEMA)

    assert operation is not None
    assert operation.vertical == "accounting"
    assert operation.scopes == ("accounting.tax_rates.read",)


def test_operation_classification_prefers_scopes_over_two_tags() -> None:
    operation = find_operation("banking", "accounts", "list", SAMPLE_SCHEMA)

    assert operation is not None
    assert operation.vertical == "banking"
    assert operation.entity == "accounts"
    assert operation.scopes == ("banking.accounts.read",)


def test_operation_classification_unifies_two_part_and_three_part_scopes() -> None:
    schema = {
        "paths": {
            "/consumers/{consumer_id}/pos/customers": {
                "get": {
                    "tags": ["Point of Sale", "Customers"],
                    "summary": "List customers",
                    "operationId": "pos_list_customers",
                    "security": [
                        {
                            "mcp_auth": [
                                "pos",
                                "pos.customers",
                                "pos.customers.read",
                                "pos.read",
                            ]
                        }
                    ],
                    "responses": {
                        "200": {
                            "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}
                        }
                    },
                },
                "post": {
                    "tags": ["Point of Sale", "Customers"],
                    "summary": "Create customer",
                    "operationId": "pos_create_customer",
                    "security": [{"mcp_auth": ["pos", "pos.customers"]}],
                    "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
                },
            }
        }
    }
    list_op = find_operation("point-of-sale", "customers", "list", schema)
    create_op = find_operation("point-of-sale", "customers", "create", schema)

    assert list_op is not None
    assert create_op is not None
    assert (list_op.vertical, list_op.entity) == ("point-of-sale", "customers")
    assert (create_op.vertical, create_op.entity) == ("point-of-sale", "customers")


def test_operation_classification_falls_back_to_path_without_tags_or_scopes() -> None:
    operation = find_operation("payment", "transactions", "list", SAMPLE_SCHEMA)

    assert operation is not None
    assert operation.vertical == "payment"
    assert operation.entity == "transactions"


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


def test_load_schema_refreshes_stale_cache_in_background(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "schema_refresh_interval_seconds", 1)
    monkeypatch.setattr("chift_cli.schema._BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS", False)
    cached_schema = {"paths": {"/cached": {"get": {"tags": ["Cached"]}}}}
    refreshed_schema = {"paths": {"/refreshed": {"get": {"tags": ["Refreshed"]}}}}
    path = save_schema(cached_schema)
    stale_time = time.time() - 5
    os.utime(path, (stale_time, stale_time))
    calls: dict[str, float] = {}

    def fake_update_schema(*, timeout: float = 30.0):
        calls["timeout"] = timeout
        return save_schema(refreshed_schema), refreshed_schema

    class ImmediateThread:
        def __init__(self, *, target, args, name, daemon):
            self.target = target
            self.args = args
            self.name = name
            self.daemon = daemon

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr("chift_cli.schema.update_schema", fake_update_schema)
    monkeypatch.setattr("chift_cli.schema.threading.Thread", ImmediateThread)

    assert load_schema() == cached_schema
    assert calls == {"timeout": 30.0}
    assert json.loads(schema_path().read_text()) == refreshed_schema


def test_load_schema_does_not_refresh_fresh_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "schema_refresh_interval_seconds", 60)
    monkeypatch.setattr("chift_cli.schema._BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS", False)
    save_schema(SAMPLE_SCHEMA)

    def fail_start_background_schema_refresh():
        raise AssertionError("fresh schema should not trigger background refresh")

    monkeypatch.setattr(
        "chift_cli.schema.start_background_schema_refresh",
        fail_start_background_schema_refresh,
    )

    assert load_schema() == SAMPLE_SCHEMA
