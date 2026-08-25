from chift_cli import config
from chift_cli.schema import (
    find_operation,
    iter_operations,
    load_schema,
    response_is_collection,
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


def test_load_schema_fetches_openapi_when_cache_is_missing(monkeypatch, tmp_path, httpx_mock) -> None:
    monkeypatch.setattr(config.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "api_base_url", "https://example.test")
    monkeypatch.setattr(config.settings, "openapi_path", "/openapi.json")

    httpx_mock.add_response(url="https://example.test/openapi.json", json=SAMPLE_SCHEMA)

    assert load_schema() == SAMPLE_SCHEMA
    assert schema_path().exists()
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url == "https://example.test/openapi.json"


def _datalab_schema(scopes: list[str]) -> dict:
    return {
        "paths": {
            "/datalab/query-db": {
                "post": {
                    "tags": ["Datalab"],
                    "summary": "Query the datalab",
                    "operationId": "datalab_query_db",
                    "security": [{"mcp_auth": scopes}],
                    "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
                }
            }
        }
    }


# (url segment, api code, tag, entity). The last three verticals are the ones whose tag
# prose slugifies to something other than the name the URL and the scopes use.
SCOPE_FORMS = [
    ("accounting", "200", "Accounting", "invoices"),
    ("pos", "300", "Point of Sale", "orders"),
    ("commerce", "400", "eCommerce", "products"),
    ("pms", "800", "Property Management System", "invoices"),
]


def _both_scope_forms_schema(*, named_scopes: bool = True, coded_scopes: bool = True) -> dict:
    """One read and one write operation per vertical, in either or both scope forms."""

    def security(name: str, code: str, entity: str, *, read: bool) -> list[dict]:
        named = [name, f"{name}.{entity}"]
        coded = [code, f"{code}.{entity}"]
        if read:
            named += [f"{name}.read", f"{name}.{entity}.read"]
            coded += [f"{code}.r", f"{code}.{entity}.r"]
        scopes = (named if named_scopes else []) + (coded if coded_scopes else [])
        return [{"mcp_auth": sorted(scopes)}]

    paths = {}
    for name, code, tag, entity in SCOPE_FORMS:
        paths[f"/consumers/{{consumer_id}}/{name}/{entity}"] = {
            "post": {
                "tags": [tag, entity.title()],
                "summary": f"Create {entity}",
                "operationId": f"{name}_create_{entity}",
                "security": security(name, code, entity, read=False),
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            },
            "get": {
                "tags": [tag, entity.title()],
                "summary": f"Get {entity}",
                "operationId": f"{name}_get_{entity}",
                "security": security(name, code, entity, read=True),
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}
                },
            },
        }
    return {"paths": paths}


def test_operation_classification_ignores_api_code_scopes() -> None:
    operations = iter_operations(_both_scope_forms_schema())

    assert {(operation.vertical, operation.entity, operation.command) for operation in operations} == {
        ("accounting", "invoices", "create"),
        ("accounting", "invoices", "list"),
        ("point-of-sale", "orders", "create"),
        ("point-of-sale", "orders", "list"),
        ("e-commerce", "products", "create"),
        ("e-commerce", "products", "list"),
        ("property-management-system", "invoices", "create"),
        ("property-management-system", "invoices", "list"),
    }


def test_operation_classification_survives_named_scope_retirement() -> None:
    """The day the API sends only `200.invoices.r`, every command must keep its name."""
    with_both = iter_operations(_both_scope_forms_schema())
    coded_only = iter_operations(_both_scope_forms_schema(named_scopes=False))

    assert [(operation.vertical, operation.entity, operation.command) for operation in coded_only] == [
        (operation.vertical, operation.entity, operation.command) for operation in with_both
    ]


def test_operation_classification_gives_up_rather_than_spell_a_vertical_two_ways() -> None:
    """Tag prose reaches the vertical only when the scopes decline to name one."""
    schema = _both_scope_forms_schema(named_scopes=False, coded_scopes=False)

    verticals = {operation.vertical for operation in iter_operations(schema)}

    assert verticals == {"accounting", "point-of-sale", "e-commerce", "property-management-system"}


def test_operation_classification_measures_entity_depth_without_the_action() -> None:
    """A `.read` on the shallower entity must not make it outrank the deeper one."""
    schema = {
        "paths": {
            "/consumers/{consumer_id}/accounting/invoices/payments": {
                "get": {
                    "summary": "Get invoice payments",
                    "operationId": "accounting_get_invoice_payments",
                    "security": [{"mcp_auth": ["accounting.invoices.read", "accounting.invoices.payments"]}],
                    "responses": {
                        "200": {
                            "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}
                        }
                    },
                }
            }
        }
    }

    operations = iter_operations(schema)

    assert [(operation.vertical, operation.entity) for operation in operations] == [("accounting", "invoices-payments")]


def test_operation_classification_ignores_a_read_variant_on_one_vertical_only() -> None:
    """A `.read` on one vertical's scope must not make it win a cross-vertical tie."""
    schema = _datalab_schema(["accounting.datalab", "pos.datalab.read", "200.datalab", "300.datalab.r"])

    operations = iter_operations(schema)

    assert [(operation.vertical, operation.entity) for operation in operations] == [("datalab", "query-db")]


def test_operation_classification_reads_entity_from_code_scopes_and_vertical_from_path() -> None:
    schema = {
        "paths": {
            "/consumers/{consumer_id}/pos/orders": {
                "get": {
                    "tags": ["Point of Sale", "Orders"],
                    "summary": "Get orders",
                    "operationId": "pos_get_orders",
                    "security": [{"mcp_auth": ["300", "300.r", "300.orders", "300.orders.r"]}],
                    "responses": {
                        "200": {
                            "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}
                        }
                    },
                }
            }
        }
    }

    operations = iter_operations(schema)

    assert [(operation.vertical, operation.entity) for operation in operations] == [("point-of-sale", "orders")]


def test_operation_classification_reads_entity_from_short_action_scopes() -> None:
    schema = {
        "paths": {
            "/consumers/{consumer_id}/accounting/invoices": {
                "get": {
                    "tags": ["Accounting", "Invoices"],
                    "summary": "Get invoices",
                    "operationId": "accounting_get_invoices",
                    "security": [{"mcp_auth": ["200", "200.r", "accounting", "accounting.invoices.r"]}],
                    "responses": {
                        "200": {
                            "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}
                        }
                    },
                }
            }
        }
    }

    operations = iter_operations(schema)

    assert [(operation.vertical, operation.entity) for operation in operations] == [("accounting", "invoices")]


def test_operation_classification_falls_back_to_the_tag_and_path_when_scopes_span_verticals() -> None:
    schema = _datalab_schema(["accounting.datalab", "pos.datalab", "200.datalab", "300.datalab"])

    operations = iter_operations(schema)

    assert [(operation.vertical, operation.entity) for operation in operations] == [("datalab", "query-db")]


def test_operation_classification_falls_back_to_the_tag_and_path_when_code_scopes_span_verticals() -> None:
    schema = _datalab_schema(["200.datalab", "300.datalab"])

    operations = iter_operations(schema)

    assert [(operation.vertical, operation.entity) for operation in operations] == [("datalab", "query-db")]
