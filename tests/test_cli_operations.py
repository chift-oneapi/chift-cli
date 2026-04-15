from __future__ import annotations

import json

from typer.testing import CliRunner

from chift_cli.cli import _display_schema, app


runner = CliRunner()


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


def test_operation_accepts_consumer_id_as_positional_input() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "consumer-123", "--force", "--dry-run"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["url"].endswith("/consumers/consumer-123")


def test_operation_rejects_unknown_input_argument() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "consumer-123", "supplier_idd=2", "--force", "--dry-run"])

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Unknown input parameter `supplier_idd`."
    assert payload["error"]["details"]["unknown"] == ["supplier_idd"]
    assert "consumer_id" not in payload["error"]["details"]


def test_operation_rejects_unknown_param_option() -> None:
    result = runner.invoke(app, ["consumers", "consumers", "delete", "consumer-123", "--param", "folder_iddss=2", "--force", "--dry-run"])

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Unknown input parameter `folder_iddss`."
    assert payload["error"]["details"]["unknown"] == ["folder_iddss"]
    assert "consumer_id" not in payload["error"]["details"]


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
