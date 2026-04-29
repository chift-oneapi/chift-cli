from __future__ import annotations

import json

import typer
from typer.testing import CliRunner

from chift_cli import config
from chift_cli.cli import _display_schema, app, operation_callback, visible_operations
from chift_cli.schema import Operation


runner = CliRunner()


def _operation(vertical: str, method: str, path: str) -> Operation:
    parameters = [
        {
            "name": part[1:-1],
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        }
        for part in path.split("/")
        if part.startswith("{") and part.endswith("}")
    ]
    return Operation(
        vertical=vertical,
        entity="items",
        command=method.lower(),
        method=method,
        path=path,
        operation_id="",
        summary="",
        scopes=(),
        raw={"parameters": parameters},
    )


def _operation_app(operation: Operation) -> typer.Typer:
    local_app = typer.Typer()
    local_app.command(operation.command)(operation_callback(operation))
    return local_app


def test_operation_with_only_missing_consumer_id_returns_context_usage() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "--force"])

    assert result.exit_code == 0
    assert "This endpoint needs additional input." in result.stdout
    assert "chift consumers consumers delete <consumer_id>" in result.stdout
    assert "This is the schema of the params:" not in result.stdout


def test_operation_schema_returns_only_merged_input_schema() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "--schema"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload) == {"additionalProperties", "properties", "type"}
    assert payload["properties"] == {}


def test_operation_accepts_consumer_id_as_positional_input(monkeypatch) -> None:
    def fake_execute_operation(operation, **kwargs):
        return {"input_values": kwargs["input_values"]}

    monkeypatch.setattr("chift_cli.cli.execute_operation", fake_execute_operation)

    result = runner.invoke(
        app,
        ["consumers", "consumers", "delete", "consumer-123", "--force"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["input_values"] == {"consumer_id": "consumer-123"}


def test_operation_rejects_unknown_input_argument() -> None:
    result = runner.invoke(
        app,
        [
            "consumers",
            "consumers",
            "delete",
            "consumer-123",
            "supplier_idd=2",
            "--force",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Unknown input parameter `supplier_idd`."
    assert payload["error"]["details"]["unknown"] == ["supplier_idd"]
    assert "consumer_id" not in payload["error"]["details"]


def test_operation_rejects_unknown_param_option() -> None:
    result = runner.invoke(
        app,
        [
            "consumers",
            "consumers",
            "delete",
            "consumer-123",
            "--param",
            "folder_iddss=2",
            "--force",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Unknown input parameter `folder_iddss`."
    assert payload["error"]["details"]["unknown"] == ["folder_iddss"]
    assert "consumer_id" not in payload["error"]["details"]


def test_operation_requires_force_with_structured_error_output() -> None:
    operation = _operation(
        "accounting",
        "DELETE",
        "/consumers/{consumer_id}/accounting/clients/{client_id}",
    )

    result = runner.invoke(
        _operation_app(operation),
        ["consumer-123", "client_id=client-456"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Mutating operations require --force."
    assert payload["error"]["type"] == "ChiftCliError"


def test_allowed_operations_allows_configured_vertical_methods(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "post")
    operation = _operation(
        "accounting",
        "POST",
        "/consumers/{consumer_id}/accounting/clients",
    )

    result = runner.invoke(
        _operation_app(operation),
        ["--schema"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["properties"] == {}


def test_allowed_operations_rejects_unconfigured_vertical_methods(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "get,post")
    operation = _operation(
        "accounting",
        "DELETE",
        "/consumers/{consumer_id}/accounting/clients/{client_id}",
    )

    result = runner.invoke(
        _operation_app(operation),
        ["--schema"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Operation DELETE is not allowed."
    assert payload["error"]["details"] == {
        "allowed": ["get", "post"],
        "method": "DELETE",
        "path": "/consumers/{consumer_id}/accounting/clients/{client_id}",
    }


def test_allowed_operations_does_not_restrict_platform_methods(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "get,post")

    result = runner.invoke(
        app,
        ["consumers", "consumers", "delete", "--schema"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"additionalProperties": False, "properties": {}, "type": "object"}


def test_allowed_operations_rejects_unsupported_methods(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "get,fetch")

    result = runner.invoke(
        app,
        ["consumers", "consumers", "delete", "--schema"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Unsupported allowed operation `fetch`."
    assert payload["error"]["details"]["unsupported"] == ["fetch"]


def test_allowed_operations_is_not_a_cli_flag() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--allowed-operations" not in result.stdout


def test_dry_run_is_not_an_operation_flag() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "--help"])

    assert result.exit_code == 0
    assert "--dry-run" not in result.stdout


def test_visible_operations_filters_by_allowed_operations(monkeypatch) -> None:
    schema = {
        "paths": {
            "/consumers/{consumer_id}": {
                "delete": {
                    "tags": ["Consumers"],
                    "parameters": [
                        {
                            "name": "consumer_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                }
            },
            "/consumers/{consumer_id}/accounting/clients": {
                "get": {"tags": ["Accounting"]},
                "post": {"tags": ["Accounting"]},
            },
        }
    }
    monkeypatch.setattr(config.settings, "allowed_operations", "post")
    monkeypatch.setattr(config.settings, "show_platform_endpoints", True)
    monkeypatch.setattr("chift_cli.cli.load_schema", lambda: schema)

    operations = visible_operations()
    accounting_methods = {
        operation.method for operation in operations if operation.vertical == "accounting"
    }
    consumer_methods = {
        operation.method for operation in operations if operation.vertical == "consumers"
    }

    assert accounting_methods == {"POST"}
    assert consumer_methods == {"DELETE"}


def test_operation_rejects_extra_positional_arguments() -> None:
    operation = _operation(
        "accounting",
        "GET",
        "/consumers/{consumer_id}/accounting/suppliers/{supplier_id}",
    )

    result = runner.invoke(
        _operation_app(operation),
        ["consumer-1", "supplier-2", "stray-extra", "another-extra"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"].startswith(
        "Unexpected positional argument `stray-extra`."
    )
    assert payload["error"]["details"]["extras"] == ["stray-extra", "another-extra"]


def test_cursor_limit_and_all_options_are_removed() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "--help"])

    assert result.exit_code == 0
    assert "--cursor" not in result.stdout
    assert "--limit" not in result.stdout
    assert "--all " not in result.stdout
    assert "--all\n" not in result.stdout


def test_display_schema_keeps_non_consumer_params() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"consumer_id": {"type": "string"}, "name": {"type": "string"}},
        "required": ["consumer_id", "name"],
    }

    assert _display_schema(schema) == {
        "type": "object",
        "additionalProperties": False,
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
