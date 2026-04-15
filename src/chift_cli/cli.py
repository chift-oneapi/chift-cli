from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from .auth import fetch_token
from .auth_form import prompt_auth_credentials
from .client import execute_operation
from .config import ApiKeyCredentials, endpoint_visible, save_api_key_credentials
from .errors import ChiftCliError
from .output import OutputFormat, emit, emit_error
from .schema import (
    DESTRUCTIVE_METHODS,
    Operation,
    iter_operations,
    load_schema,
    schema_age_seconds,
    search_schema,
    tree,
    update_schema,
)


app = typer.Typer(
    no_args_is_help=True,
    help="OpenAPI-driven CLI for the Chift API.",
    rich_markup_mode=None,
)
auth_app = typer.Typer(
    no_args_is_help=True, help="Authenticate with Chift.", rich_markup_mode=None
)
schema_app = typer.Typer(
    no_args_is_help=True,
    help="Inspect and refresh the local OpenAPI schema.",
    rich_markup_mode=None,
)

app.add_typer(auth_app, name="auth")
app.add_typer(schema_app, name="schema")


OutputOption = Annotated[
    OutputFormat, typer.Option("--output", "-o", help="Machine-readable output format.")
]
DebugOption = Annotated[
    bool, typer.Option("--debug", help="Write debug logs to stderr.")
]


def visible_operations() -> list[Operation]:
    return [
        operation
        for operation in iter_operations(load_schema())
        if endpoint_visible(operation.vertical)
    ]


def _path_parameter_names(path: str) -> list[str]:
    return [
        part[1:-1]
        for part in path.split("/")
        if part.startswith("{") and part.endswith("}")
    ]


def _provided_parameters(params: list[str] | None) -> set[str]:
    return {value.split("=", 1)[0] for value in params or [] if "=" in value}


def _provided_parameter_names(
    input_args: list[str] | None, params: list[str] | None
) -> set[str]:
    names = _provided_parameters(params)
    for item in input_args or []:
        if "=" in item:
            names.add(item.split("=", 1)[0])
    return names


def _input_values_from_args(
    operation: Operation, input_args: list[str] | None, params: list[str] | None
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    unnamed = []
    for item in input_args or []:
        if "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
        else:
            unnamed.append(item)
    path_names = _path_parameter_names(operation.path)
    provided = _provided_parameters(params) | set(values)
    missing_path_names = [name for name in path_names if name not in provided]
    for name, value in zip(missing_path_names, unnamed):
        values[name] = value
    return values


def _json_schema_for_parameter(parameter: dict[str, Any]) -> dict[str, Any]:
    schema = dict(parameter.get("schema") or {})
    if parameter.get("description"):
        schema["description"] = parameter["description"]
    return schema or {"type": "string"}


def _request_body_schema(operation: Operation) -> dict[str, Any]:
    content = (operation.raw.get("requestBody") or {}).get("content") or {}
    schema = content.get("application/json", {}).get("schema")
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        name = ref.rsplit("/", 1)[-1]
        return operation.components.get("schemas", {}).get(name, schema)
    return schema


def _display_schema(schema: dict[str, Any]) -> dict[str, Any]:
    display = {**schema, "properties": dict(schema.get("properties") or {})}
    display["properties"].pop("consumer_id", None)
    required = [name for name in display.get("required", []) if name != "consumer_id"]
    if required:
        display["required"] = required
    else:
        display.pop("required", None)
    return display


def input_schema(operation: Operation) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    routing: dict[str, str] = {}
    for parameter in operation.raw.get("parameters") or []:
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or location not in {"path", "query"}:
            continue
        properties[name] = _json_schema_for_parameter(parameter)
        routing[name] = location
        if parameter.get("required"):
            required.append(name)
    body_schema = _request_body_schema(operation)
    if body_schema.get("type") == "object":
        for name, schema in (body_schema.get("properties") or {}).items():
            properties.setdefault(name, schema)
            routing.setdefault(name, "body")
        for name in body_schema.get("required") or []:
            if name not in required:
                required.append(name)
    elif body_schema:
        properties["body"] = body_schema
        routing["body"] = "body"
        if (operation.raw.get("requestBody") or {}).get("required"):
            required.append("body")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return {"json_schema": schema, "routing": routing}


def endpoint_schema(operation: Operation) -> dict:
    inputs = input_schema(operation)
    return {
        "endpoint": {
            "vertical": operation.vertical,
            "entity": operation.entity,
            "command": operation.command,
            "method": operation.method,
            "path": operation.path,
            "summary": operation.summary,
            "operation_id": operation.operation_id,
            "scopes": list(operation.scopes),
        },
        "input": inputs,
        "usage": {
            "params": "--param field=value",
            "consumer_id": "You can pass consumer_id as the first argument.",
            "filters": "--filter field=value",
            "fields": "--fields field1,nested.field",
        },
        "responses": operation.raw.get("responses"),
    }


def _input_usage(operation: Operation, schema: dict[str, Any]) -> str:
    placeholders = (
        ["<consumer_id>"] if "consumer_id" in schema.get("required", []) else []
    )
    parts = [
        "chift",
        operation.vertical,
        operation.entity,
        operation.command,
        *placeholders,
    ]
    options = ["[--fields field1,nested.field]", "[--filter field=value]"]
    display_schema = _display_schema(schema)
    if display_schema.get("properties"):
        options.append("[--param field=value]")
    return " ".join([*parts, *options])


def emit_missing_input_guidance(operation: Operation, schema: dict[str, Any]) -> None:
    display_schema = _display_schema(schema)
    typer.echo("This endpoint needs additional input. Provide it as follows:")
    typer.echo()
    typer.echo(f"  {_input_usage(operation, schema)}")
    if display_schema.get("properties"):
        typer.echo()
        typer.echo("This is the schema of the params:")
        typer.echo()
        typer.echo(json.dumps(display_schema, indent=2, sort_keys=True))


def validate_input_names(
    operation: Operation,
    input_args: list[str] | None,
    params: list[str] | None,
    schema: dict[str, Any],
) -> None:
    allowed = set(schema.get("properties") or {})
    provided = _provided_parameter_names(input_args, params)
    unknown = sorted(provided - allowed)
    if unknown:
        display_allowed = sorted(name for name in allowed if name != "consumer_id")
        raise ChiftCliError(
            f"Unknown input parameter `{unknown[0]}`.",
            details={
                "unknown": unknown,
                "accepted": display_allowed,
            },
        )


def exit_with_error(exc: ChiftCliError) -> None:
    emit_error(exc)
    raise typer.Exit(exc.exit_code) from None


@auth_app.command("setup")
def auth_setup(
    account_id: Annotated[
        str | None,
        typer.Option(
            "--account-id", envvar="CHIFT_ACCOUNT_ID", help="Chift accountId."
        ),
    ] = None,
    client_id: Annotated[
        str | None,
        typer.Option("--client-id", envvar="CHIFT_CLIENT_ID", help="Chift clientId."),
    ] = None,
    client_secret: Annotated[
        str | None,
        typer.Option(
            "--client-secret", envvar="CHIFT_CLIENT_SECRET", help="Chift clientSecret."
        ),
    ] = None,
    debug: DebugOption = False,
) -> None:
    interactive = not all([account_id, client_id, client_secret])
    if interactive:
        values = prompt_auth_credentials(
            account_id=account_id, client_id=client_id, client_secret=client_secret
        )
        account_id = values.account_id
        client_id = values.client_id
        client_secret = values.client_secret
    if not client_id or not client_secret or not account_id:
        raise ChiftCliError("Client ID, client secret, and account ID are required.")
    credentials = ApiKeyCredentials(
        client_id=client_id, client_secret=client_secret, account_id=account_id
    )
    try:
        save_api_key_credentials(credentials)
        fetch_token(credentials, debug=debug)
    except ChiftCliError as exc:
        typer.secho(exc.message, err=True, fg=typer.colors.RED)
        raise typer.Exit(exc.exit_code) from None
    typer.secho("Chift authentication configured.", fg=typer.colors.GREEN)


@schema_app.command("update")
def schema_update(output: OutputOption = "json") -> None:
    path, data = update_schema()
    emit(
        {
            "status": "ok",
            "path": str(path),
            "version": data.get("info", {}).get("version"),
            "paths": len(data.get("paths", {})),
        },
        output,
    )


@schema_app.command("tree")
def schema_tree(output: OutputOption = "json") -> None:
    emit({"schema_age_seconds": schema_age_seconds(), "tree": tree()}, output)


@schema_app.command("search")
def schema_search(query: str, output: OutputOption = "json") -> None:
    emit({"query": query, "matches": search_schema(query)}, output)


def operation_callback(operation: Operation):
    def callback(
        input_args: Annotated[
            list[str] | None,
            typer.Argument(
                help="Input values. Use a bare value for consumer_id, or KEY=VALUE."
            ),
        ] = None,
        params: Annotated[
            list[str] | None,
            typer.Option(
                "--param",
                "-p",
                help="Parameter as KEY=VALUE. Path params are filled first; the rest become query params.",
            ),
        ] = None,
        body: Annotated[
            str | None, typer.Option("--json", help="Raw JSON request body.")
        ] = None,
        fields: Annotated[
            str | None,
            typer.Option(
                "--fields",
                help="Comma-separated fields to keep, including nested paths.",
            ),
        ] = None,
        filters: Annotated[
            list[str] | None,
            typer.Option(
                "--filter", help="Client-side filter as KEY=VALUE; can be repeated."
            ),
        ] = None,
        cursor: Annotated[
            str | None,
            typer.Option(
                "--cursor", help="Pagination cursor, added as a query parameter."
            ),
        ] = None,
        limit: Annotated[
            int | None,
            typer.Option(
                "--limit", help="Pagination limit, added as a query parameter."
            ),
        ] = None,
        all_pages: Annotated[
            bool,
            typer.Option(
                "--all",
                help="Reserved for auto-pagination once cursor names are known.",
            ),
        ] = False,
        schema: Annotated[
            bool,
            typer.Option(
                "--schema", help="Return this endpoint schema instead of executing it."
            ),
        ] = False,
        dry_run: Annotated[
            bool,
            typer.Option(
                "--dry-run", "-n", help="Print the request without sending it."
            ),
        ] = False,
        force: Annotated[
            bool, typer.Option("--force", help="Required for mutating operations.")
        ] = False,
        output: OutputOption = "json",
        debug: DebugOption = False,
    ) -> None:
        if schema:
            emit(_display_schema(input_schema(operation)["json_schema"]), output)
            return
        if operation.method.lower() in DESTRUCTIVE_METHODS and not (force or dry_run):
            raise ChiftCliError(
                "Mutating operations require --force. Use --dry-run to inspect the request."
            )
        merged_params = list(params or [])
        if cursor:
            merged_params.append(f"cursor={cursor}")
        if limit is not None:
            merged_params.append(f"limit={limit}")
        if all_pages:
            merged_params.append("all=true")
        input_values = _input_values_from_args(operation, input_args, merged_params)
        merged_schema = input_schema(operation)["json_schema"]
        try:
            validate_input_names(operation, input_args, merged_params, merged_schema)
        except ChiftCliError as exc:
            exit_with_error(exc)
        provided_inputs = _provided_parameters(merged_params) | set(input_values)
        missing_required = [
            name
            for name in merged_schema.get("required", [])
            if name not in provided_inputs
        ]
        if missing_required:
            emit_missing_input_guidance(operation, merged_schema)
            return
        emit(
            execute_operation(
                operation,
                params=merged_params,
                body=body,
                fields=fields,
                filters=filters,
                dry_run=dry_run,
                debug=debug,
                input_values=input_values,
            ),
            output,
        )

    callback.__name__ = operation.command.replace("-", "_")
    callback.__doc__ = f"{operation.method} {operation.path}\n\n{operation.summary}"
    return callback


def register_dynamic_commands() -> None:
    vertical_apps: dict[str, typer.Typer] = {}
    entity_apps: dict[tuple[str, str], typer.Typer] = {}
    for operation in visible_operations():
        vertical_app = vertical_apps.get(operation.vertical)
        if vertical_app is None:
            vertical_app = typer.Typer(
                no_args_is_help=True,
                help=f"{operation.vertical} endpoints.",
                rich_markup_mode=None,
            )
            app.add_typer(vertical_app, name=operation.vertical)
            vertical_apps[operation.vertical] = vertical_app
        entity_key = (operation.vertical, operation.entity)
        entity_app = entity_apps.get(entity_key)
        if entity_app is None:
            entity_app = typer.Typer(
                no_args_is_help=True,
                help=f"{operation.entity} endpoints.",
                rich_markup_mode=None,
            )
            vertical_app.add_typer(entity_app, name=operation.entity)
            entity_apps[entity_key] = entity_app
        entity_app.command(
            operation.command, help=f"{operation.method} {operation.path}"
        )(operation_callback(operation))


def main() -> None:
    try:
        app()
    except ChiftCliError as exc:
        emit_error(exc)
        raise SystemExit(exc.exit_code) from None


register_dynamic_commands()
