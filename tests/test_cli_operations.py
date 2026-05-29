from __future__ import annotations

import json
import subprocess

import typer
from typer.testing import CliRunner

from chift_cli import config
from chift_cli.cli import (
    INSTALL_SCRIPT_URL,
    INSTALL_SCRIPT_URL_PS1,
    _display_schema,
    app,
    operation_allowed_class,
    operation_callback,
    visible_operations,
)
from chift_cli.schema import Operation

runner = CliRunner()


def _operation(
    vertical: str,
    method: str,
    path: str,
    scopes: tuple[str, ...] = (),
    *,
    body_schema: dict | None = None,
) -> Operation:
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
    raw: dict = {"parameters": parameters}
    if body_schema is not None:
        raw["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": body_schema}},
        }
    return Operation(
        vertical=vertical,
        entity="items",
        command=method.lower(),
        method=method,
        path=path,
        operation_id="",
        summary="",
        scopes=scopes,
        raw=raw,
    )


def _operation_app(operation: Operation) -> typer.Typer:
    local_app = typer.Typer()
    local_app.command(operation.command)(operation_callback(operation))
    return local_app


def test_operation_with_only_missing_consumer_id_returns_context_usage() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "--force"])

    assert result.exit_code == 2
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


def test_allowed_operations_allows_configured_vertical_classes(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "write")
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


def test_allowed_operations_rejects_unconfigured_vertical_classes(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "read,write")
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
    assert payload["error"]["message"] == "Operation class `dangerous` is not allowed."
    assert payload["error"]["details"] == {
        "allowed": ["read", "write"],
        "class": "dangerous",
        "method": "DELETE",
        "path": "/consumers/{consumer_id}/accounting/clients/{client_id}",
    }


def test_allowed_operations_does_not_restrict_platform_methods(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "read,write")

    result = runner.invoke(
        app,
        ["consumers", "consumers", "delete", "--schema"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"additionalProperties": False, "properties": {}, "type": "object"}


def test_allowed_operations_rejects_unsupported_classes(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "get,fetch")

    result = runner.invoke(
        app,
        ["consumers", "consumers", "delete", "--schema"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Unsupported allowed operation `fetch`."
    assert payload["error"]["details"]["unsupported"] == ["fetch", "get"]


def test_allowed_operations_is_not_a_cli_flag() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--allowed-operations" not in result.stdout


def test_dynamic_vertical_group_without_subcommand_shows_help_successfully() -> None:
    result = runner.invoke(app, ["consumers"])

    assert result.exit_code == 0
    assert "consumers endpoints." in result.stdout
    assert "Commands" in result.stdout


def test_dynamic_entity_group_without_subcommand_shows_help_successfully() -> None:
    result = runner.invoke(app, ["consumers", "consumers"])

    assert result.exit_code == 0
    assert "consumers endpoints." in result.stdout
    assert "delete" in result.stdout


def test_dynamic_group_keeps_invalid_subcommand_as_usage_error() -> None:
    result = runner.invoke(app, ["consumers", "nope"])

    assert result.exit_code == 2
    assert "No such command" in result.stderr


def test_dry_run_is_not_an_operation_flag() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "--help"])

    assert result.exit_code == 0
    assert "--dry-run" not in result.stdout


def test_visible_operations_filters_by_allowed_operation_classes(monkeypatch) -> None:
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
    monkeypatch.setattr(config.settings, "allowed_operations", "write")
    monkeypatch.setattr(config.settings, "show_platform_endpoints", True)
    monkeypatch.setattr("chift_cli.cli.load_schema", lambda: schema)

    operations = visible_operations()
    accounting_methods = {operation.method for operation in operations if operation.vertical == "accounting"}
    consumer_methods = {operation.method for operation in operations if operation.vertical == "consumers"}

    assert accounting_methods == {"POST"}
    assert consumer_methods == {"DELETE"}


def test_read_only_mode_includes_mixed_scope_operations(monkeypatch) -> None:
    # Operations whose scope list contains a .read scope alongside a broad parent scope
    # must survive CHIFT_ALLOWED_OPERATIONS=read — this was the original bug.
    schema = {
        "paths": {
            "/consumers/{consumer_id}/accounting/suppliers": {
                "get": {
                    "tags": ["Accounting"],
                    "security": [{"oauth2": ["accounting.suppliers", "accounting.suppliers.read"]}],
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
            "/consumers/{consumer_id}/accounting/suppliers/{supplier_id}": {
                "post": {
                    "tags": ["Accounting"],
                    "security": [{"oauth2": ["accounting.suppliers"]}],
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
        }
    }
    monkeypatch.setattr(config.settings, "allowed_operations", "read")
    monkeypatch.setattr("chift_cli.cli.load_schema", lambda: schema)

    operations = visible_operations()
    methods = {op.method for op in operations if op.vertical == "accounting"}

    assert "GET" in methods
    assert "POST" not in methods


def test_read_only_mode_allows_mixed_scope_operation_callback(monkeypatch) -> None:
    # Callback must not reject an operation that carries both a broad scope and a .read scope.
    monkeypatch.setattr(config.settings, "allowed_operations", "read")
    operation = _operation(
        "accounting",
        "GET",
        "/consumers/{consumer_id}/accounting/suppliers",
        scopes=("accounting.suppliers", "accounting.suppliers.read"),
    )

    result = runner.invoke(
        _operation_app(operation),
        ["--schema"],
    )

    assert result.exit_code == 0


def test_allowed_operations_all_allows_vertical_classes(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "allowed_operations", "all")
    operation = _operation(
        "accounting",
        "DELETE",
        "/consumers/{consumer_id}/accounting/clients/{client_id}",
    )

    result = runner.invoke(
        _operation_app(operation),
        ["--schema"],
    )

    assert result.exit_code == 0


def test_operation_allowed_class_uses_read_scopes_before_method() -> None:
    operation = _operation(
        "accounting",
        "POST",
        "/consumers/{consumer_id}/accounting/reports",
        scopes=("accounting.reports.read",),
    )

    assert operation_allowed_class(operation) == "read"


def test_operation_allowed_class_uses_broad_scopes_before_method() -> None:
    operation = _operation(
        "accounting",
        "GET",
        "/consumers/{consumer_id}/accounting/reports",
        scopes=("accounting.reports",),
    )

    assert operation_allowed_class(operation) == "write"


def test_operation_allowed_class_mixed_scopes_read_wins() -> None:
    # Chift sends both the broad parent scope and a .read scope together.
    # A single .read scope is enough to classify the operation as read.
    operation = _operation(
        "accounting",
        "GET",
        "/consumers/{consumer_id}/accounting/suppliers",
        scopes=("accounting.suppliers", "accounting.suppliers.read"),
    )

    assert operation_allowed_class(operation) == "read"


def test_operation_allowed_class_mixed_scopes_delete_with_read_scope_is_read() -> None:
    # Even a DELETE that carries a .read scope alongside a broad scope is read-classified.
    operation = _operation(
        "accounting",
        "DELETE",
        "/consumers/{consumer_id}/accounting/suppliers/{supplier_id}",
        scopes=("accounting.suppliers", "accounting.suppliers.read"),
    )

    assert operation_allowed_class(operation) == "read"


def test_operation_allowed_class_treats_broad_scoped_delete_as_dangerous() -> None:
    operation = _operation(
        "accounting",
        "DELETE",
        "/consumers/{consumer_id}/accounting/reports/{report_id}",
        scopes=("accounting.reports",),
    )

    assert operation_allowed_class(operation) == "dangerous"


def test_operation_allowed_class_classifies_mixed_scopes_as_read() -> None:
    operation = _operation(
        "accounting",
        "GET",
        "/consumers/{consumer_id}/accounting/suppliers",
        scopes=(
            "accounting",
            "accounting.suppliers",
            "accounting.suppliers.read",
            "accounting.read",
        ),
    )

    assert operation_allowed_class(operation) == "read"


def test_operation_allowed_class_falls_back_to_http_methods_without_scopes() -> None:
    assert operation_allowed_class(_operation("accounting", "OPTIONS", "/consumers/{consumer_id}/accounting")) == "read"
    assert operation_allowed_class(_operation("accounting", "PATCH", "/consumers/{consumer_id}/accounting")) == "write"
    assert (
        operation_allowed_class(_operation("accounting", "DELETE", "/consumers/{consumer_id}/accounting"))
        == "dangerous"
    )


def test_operation_accepts_required_body_fields_via_json_flag(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute_operation(operation, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("chift_cli.cli.execute_operation", fake_execute_operation)
    operation = _operation(
        "accounting",
        "POST",
        "/consumers/{consumer_id}/accounting/suppliers",
        body_schema={
            "type": "object",
            "required": ["name", "addresses"],
            "properties": {
                "name": {"type": "string"},
                "addresses": {"type": "array", "items": {"type": "object"}},
            },
        },
    )

    result = runner.invoke(
        _operation_app(operation),
        [
            "consumer-1",
            "--force",
            "--json",
            '{"name":"Acme","addresses":[]}',
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True}
    assert captured["body"] == '{"name":"Acme","addresses":[]}'


def test_operation_rejects_invalid_json_body_with_argument_error(monkeypatch) -> None:
    calls: list = []

    def fake_execute_operation(operation, **kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr("chift_cli.cli.execute_operation", fake_execute_operation)
    operation = _operation(
        "accounting",
        "POST",
        "/consumers/{consumer_id}/accounting/suppliers",
        body_schema={
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
    )

    result = runner.invoke(
        _operation_app(operation),
        ["consumer-1", "--force", "--json", "{not json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Invalid JSON body."
    assert calls == []


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
    assert payload["error"]["message"].startswith("Unexpected positional argument `stray-extra`.")
    assert payload["error"]["details"]["extras"] == ["stray-extra", "another-extra"]


def test_update_stops_when_installer_download_fails(monkeypatch) -> None:
    calls: list[tuple[list[str], dict]] = []

    # Force the POSIX update path regardless of the host OS running the test.
    monkeypatch.setattr("chift_cli.cli.sys.platform", "linux")
    monkeypatch.setattr("chift_cli.cli.shutil.which", lambda cmd: f"/usr/bin/{cmd}")

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args == ["curl", "-fsSL", INSTALL_SCRIPT_URL]:
            return subprocess.CompletedProcess(args, 22, stdout=b"", stderr=b"404")
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr("chift_cli.cli.subprocess.run", fake_run)

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 22
    assert "Update failed." in result.stderr
    assert [call[0] for call in calls] == [
        ["curl", "-fsSL", INSTALL_SCRIPT_URL],
    ]


def test_update_uses_powershell_on_windows(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr("chift_cli.cli.sys.platform", "win32")
    monkeypatch.setattr(
        "chift_cli.cli.shutil.which",
        lambda cmd: r"C:\\pwsh.exe" if cmd == "pwsh" else None,
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("chift_cli.cli.subprocess.run", fake_run)

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0][0] == r"C:\\pwsh.exe"
    assert calls[0][-1] == f"irm {INSTALL_SCRIPT_URL_PS1} | iex"


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
