import json
import shutil
import subprocess
import sys
from typing import Annotated, Any

import typer

from .auth import fetch_token
from .auth_form import prompt_auth_credentials
from .client import execute_operation, parse_json_body
from .config import (
    INTERNAL_ENDPOINTS,
    PLATFORM_ENDPOINTS,
    ApiKeyCredentials,
    endpoint_visible,
    load_api_key_credentials,
    save_api_key_credentials,
    settings,
)
from .errors import AUTHENTICATION_ERROR, ChiftCliError
from .output import OutputFormat, emit, emit_error
from .pathing import path_parameter_names
from .schema import (
    DESTRUCTIVE_METHODS,
    Operation,
    iter_operations,
    load_schema,
    resolve_refs_deep,
    schema_age_seconds,
    search_schema,
    tree,
    update_schema,
)

app = typer.Typer(
    no_args_is_help=False,
    help="CLI for the Chift API.",
    rich_markup_mode=None,
)
auth_app = typer.Typer(
    no_args_is_help=True,
    help="Configure and validate Chift API credentials.",
    rich_markup_mode=None,
)
schema_app = typer.Typer(
    no_args_is_help=True,
    help="Inspect and refresh the local OpenAPI schema.",
    rich_markup_mode=None,
)

app.add_typer(auth_app, name="auth")
app.add_typer(schema_app, name="schema")


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
    next_step: Annotated[
        bool,
        typer.Option("--next", help="Show what to do next."),
    ] = False,
) -> None:
    if next_step or ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


OutputOption = Annotated[OutputFormat, typer.Option("--output", "-o", help="Machine-readable output format.")]
DebugOption = Annotated[bool, typer.Option("--debug", help="Write debug logs to stderr.")]
CHIFT_API_KEYS_URL = "https://chift.app/api-keys"
ALLOWED_OPERATION_CLASSES = {"all", "dangerous", "read", "write"}
READ_METHODS = {"get", "head", "options"}
WRITE_METHODS = {"patch", "post", "put"}
DANGEROUS_METHODS = {"delete"}


def parse_allowed_operations(value: str | None) -> set[str] | None:
    if value is None or not value.strip():
        return None
    operations = {item.strip().lower() for item in value.split(",") if item.strip()}
    if not operations:
        return None
    unsupported = sorted(operations - ALLOWED_OPERATION_CLASSES)
    if unsupported:
        raise ChiftCliError(
            f"Unsupported allowed operation `{unsupported[0]}`.",
            details={
                "unsupported": unsupported,
                "accepted": sorted(ALLOWED_OPERATION_CLASSES),
            },
        )
    if "all" in operations:
        return None
    return operations


def configured_allowed_operations() -> set[str] | None:
    return parse_allowed_operations(settings.allowed_operations)


def allowed_operation_filter() -> set[str] | None:
    try:
        return configured_allowed_operations()
    except ChiftCliError:
        return None


def operation_uses_allowed_operations(operation: Operation) -> bool:
    return operation.vertical not in (INTERNAL_ENDPOINTS | PLATFORM_ENDPOINTS)


def group_with_successful_help(*, help: str) -> typer.Typer:
    group = typer.Typer(
        no_args_is_help=False,
        invoke_without_command=True,
        help=help,
        rich_markup_mode=None,
    )

    @group.callback()
    def show_help_on_empty_group(
        ctx: typer.Context,
        next_step: Annotated[
            bool,
            typer.Option("--next", help="Show what to do next."),
        ] = False,
    ) -> None:
        if next_step or ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

    return group


def operation_allowed_class(operation: Operation) -> str:
    method = operation.method.lower()
    if operation.scopes:
        any_read_scope = any(scope.split(".")[-1] == "read" for scope in operation.scopes)
        if any_read_scope:
            return "read"
        return "dangerous" if method in DANGEROUS_METHODS else "write"
    if method in READ_METHODS:
        return "read"
    if method in WRITE_METHODS:
        return "write"
    if method in DANGEROUS_METHODS:
        return "dangerous"
    return "dangerous"


def visible_operations() -> list[Operation]:
    allowed_operations = allowed_operation_filter()
    return [
        operation
        for operation in iter_operations(load_schema())
        if endpoint_visible(operation.vertical)
        and (
            allowed_operations is None
            or not operation_uses_allowed_operations(operation)
            or operation_allowed_class(operation) in allowed_operations
        )
    ]


def _provided_parameters(params: list[str] | None) -> set[str]:
    return {value.split("=", 1)[0] for value in params or [] if "=" in value}


def _provided_parameter_names(input_args: list[str] | None, params: list[str] | None) -> set[str]:
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
    if settings.consumer_id and "consumer_id" not in values:
        values["consumer_id"] = settings.consumer_id
    path_names = path_parameter_names(operation.path)
    provided = _provided_parameters(params) | set(values)
    missing_path_names = [name for name in path_names if name not in provided]
    if len(unnamed) > len(missing_path_names):
        extras = unnamed[len(missing_path_names) :]
        raise ChiftCliError(
            f"Unexpected positional argument `{extras[0]}`. Pass endpoint inputs as KEY=VALUE.",
            details={
                "extras": extras,
                "expected_path_parameters": missing_path_names,
            },
        )
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
    document = {"components": operation.components}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in operation.raw.get("parameters") or []:
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or location not in {"path", "query"}:
            continue
        param_schema = _json_schema_for_parameter(parameter)
        properties[name] = resolve_refs_deep(param_schema, document)
        if parameter.get("required"):
            required.append(name)
    body_schema = _request_body_schema(operation)
    if body_schema.get("type") == "object":
        for name, schema in (body_schema.get("properties") or {}).items():
            properties.setdefault(name, resolve_refs_deep(schema, document))
        for name in body_schema.get("required") or []:
            if name not in required:
                required.append(name)
    elif body_schema:
        properties["body"] = resolve_refs_deep(body_schema, document)
        if (operation.raw.get("requestBody") or {}).get("required"):
            required.append("body")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _input_usage(operation: Operation, schema: dict[str, Any]) -> str:
    placeholders = ["<consumer_id>"] if "consumer_id" in schema.get("required", []) else []
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


@auth_app.command(
    "setup",
    help=(
        "Save API credentials and verify them by fetching a token. "
        f"Get an API key at {CHIFT_API_KEYS_URL}. "
        "Missing values open an interactive terminal form."
    ),
)
def auth_setup(
    account_id: Annotated[
        str | None,
        typer.Option("--account-id", envvar="CHIFT_ACCOUNT_ID", help="Chift accountId."),
    ] = None,
    client_id: Annotated[
        str | None,
        typer.Option("--client-id", envvar="CHIFT_CLIENT_ID", help="Chift clientId."),
    ] = None,
    client_secret: Annotated[
        str | None,
        typer.Option("--client-secret", envvar="CHIFT_CLIENT_SECRET", help="Chift clientSecret."),
    ] = None,
    debug: DebugOption = False,
) -> None:
    """Store Chift API credentials for future CLI calls.

    Get an API key at https://chift.app/api-keys.

    Missing values open an interactive terminal form. Pass all credential flags
    or environment variables for non-interactive use.
    """
    interactive = not all([account_id, client_id, client_secret])
    if interactive:
        values = prompt_auth_credentials(account_id=account_id, client_id=client_id, client_secret=client_secret)
        account_id = values.account_id
        client_id = values.client_id
        client_secret = values.client_secret
    if not client_id or not client_secret or not account_id:
        raise ChiftCliError("Client ID, client secret, and account ID are required.")
    credentials = ApiKeyCredentials(client_id=client_id, client_secret=client_secret, account_id=account_id)
    try:
        fetch_token(credentials, debug=debug)
        save_api_key_credentials(credentials)
    except ChiftCliError as exc:
        typer.secho(exc.message, err=True, fg=typer.colors.RED)
        raise typer.Exit(exc.exit_code) from None
    typer.secho("Chift authentication configured.", fg=typer.colors.GREEN)


@auth_app.command(
    "check",
    help=(
        "Validate saved API credentials by fetching a fresh token. "
        "This checks Chift accepts the configured credentials instead of only "
        "inspecting the local token cache."
    ),
)
def auth_check(debug: DebugOption = False) -> None:
    """Check whether the saved credentials are still accepted by Chift.

    This command uses the configured API credentials and requests a fresh token,
    so it validates the credentials instead of only inspecting the local cache.
    """
    credentials = load_api_key_credentials()
    if not credentials:
        typer.secho(
            "No API credentials found. Run `chift auth setup` first.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(AUTHENTICATION_ERROR)
    try:
        fetch_token(credentials, debug=debug)
    except ChiftCliError as exc:
        typer.secho(exc.message, err=True, fg=typer.colors.RED)
        raise typer.Exit(exc.exit_code) from None
    typer.secho("Chift authentication valid.", fg=typer.colors.GREEN)


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
            typer.Argument(help="Input values. Use a bare value for consumer_id, or KEY=VALUE."),
        ] = None,
        params: Annotated[
            list[str] | None,
            typer.Option(
                "--param",
                "-p",
                help="Parameter as KEY=VALUE. Path params are filled first; the rest become query params.",
            ),
        ] = None,
        body: Annotated[str | None, typer.Option("--json", help="Raw JSON request body.")] = None,
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
                "--filter", help="Client-side filter as KEY=VALUE; can be repeated. All filters must match (AND)."
            ),
        ] = None,
        schema: Annotated[
            bool,
            typer.Option("--schema", help="Return this endpoint schema instead of executing it."),
        ] = False,
        next_step: Annotated[
            bool,
            typer.Option("--next", help="Show what inputs this endpoint needs to run."),
        ] = False,
        force: Annotated[bool, typer.Option("--force", help="Required for mutating operations.")] = False,
        output: OutputOption = "json",
        debug: DebugOption = False,
    ) -> None:
        try:
            allowed_operations = configured_allowed_operations()
        except ChiftCliError as exc:
            exit_with_error(exc)
        if (
            allowed_operations is not None
            and operation_uses_allowed_operations(operation)
            and operation_allowed_class(operation) not in allowed_operations
        ):
            operation_class = operation_allowed_class(operation)
            exit_with_error(
                ChiftCliError(
                    f"Operation class `{operation_class}` is not allowed.",
                    details={
                        "allowed": sorted(allowed_operations),
                        "class": operation_class,
                        "method": operation.method,
                        "path": operation.path,
                    },
                )
            )
        if next_step or schema:
            emit(_display_schema(input_schema(operation)), output)
            return
        if operation.method.lower() in DESTRUCTIVE_METHODS and not force:
            exit_with_error(ChiftCliError("Mutating operations require --force."))
        merged_params = list(params or [])
        try:
            input_values = _input_values_from_args(operation, input_args, merged_params)
            merged_schema = input_schema(operation)
            validate_input_names(operation, input_args, merged_params, merged_schema)
            parsed_body = parse_json_body(body)
        except ChiftCliError as exc:
            exit_with_error(exc)
        provided_inputs = _provided_parameters(merged_params) | set(input_values)
        if isinstance(parsed_body, dict):
            provided_inputs |= set(parsed_body.keys())
        missing_required = [name for name in merged_schema.get("required", []) if name not in provided_inputs]
        if missing_required:
            emit_missing_input_guidance(operation, merged_schema)
            raise typer.Exit(2)
        emit(
            execute_operation(
                operation,
                params=merged_params,
                body=body,
                fields=fields,
                filters=filters,
                debug=debug,
                input_values=input_values,
            ),
            output,
        )

    callback.__name__ = operation.command.replace("-", "_")
    callback.__doc__ = f"{operation.method} {operation.path}\n\n{operation.summary}"
    return callback


def register_dynamic_commands() -> None:
    all_ops = visible_operations()
    vertical_apps: dict[str, typer.Typer] = {}
    entity_apps: dict[tuple[str, str], typer.Typer] = {}
    for operation in all_ops:
        vertical = operation.vertical
        vertical_app = vertical_apps.get(vertical)
        if vertical_app is None:
            vertical_app = group_with_successful_help(help=f"{vertical} endpoints.")
            app.add_typer(vertical_app, name=vertical)
            vertical_apps[vertical] = vertical_app

        entity_key = (vertical, operation.entity)
        entity_app = entity_apps.get(entity_key)
        if entity_app is None:
            entity = operation.entity
            entity_app = group_with_successful_help(help=f"{entity} endpoints.")
            vertical_app.add_typer(entity_app, name=entity)
            entity_apps[entity_key] = entity_app

        entity_app.command(operation.command, help=f"{operation.method} {operation.path}")(
            operation_callback(operation)
        )


INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/chift-oneapi/chift-cli/master/install.sh"
INSTALL_SCRIPT_URL_PS1 = "https://raw.githubusercontent.com/chift-oneapi/chift-cli/master/install.ps1"


@app.command("update", help="Update chift-cli to the latest version.")
def update() -> None:
    if sys.platform == "win32":
        _update_windows()
    else:
        _update_posix()
    typer.secho("chift-cli updated successfully.", fg=typer.colors.GREEN)


def _update_posix() -> None:
    if shutil.which("curl") is None:
        typer.secho(
            "curl is not available. Install it and retry.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.echo("Updating chift-cli...")
    download = subprocess.run(
        ["curl", "-fsSL", INSTALL_SCRIPT_URL],
        check=False,
        stdout=subprocess.PIPE,
    )
    if download.returncode != 0:
        typer.secho("Update failed.", err=True, fg=typer.colors.RED)
        raise typer.Exit(download.returncode)

    result = subprocess.run(["sh"], input=download.stdout, check=False)
    if result.returncode != 0:
        typer.secho("Update failed.", err=True, fg=typer.colors.RED)
        raise typer.Exit(result.returncode)


def _update_windows() -> None:
    powershell = _windows_powershell()
    if powershell is None:
        typer.secho(
            "PowerShell is not available. Install it and retry.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.echo("Updating chift-cli...")
    # Download the installer and pipe it into PowerShell, mirroring the
    # documented `irm ... | iex` install flow.
    command = f"irm {INSTALL_SCRIPT_URL_PS1} | iex"
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
    )
    if result.returncode != 0:
        typer.secho("Update failed.", err=True, fg=typer.colors.RED)
        raise typer.Exit(result.returncode)


def _windows_powershell() -> str | None:
    """Return an available PowerShell executable, preferring pwsh (PS 7+)."""
    for candidate in ("pwsh", "powershell"):
        path = shutil.which(candidate)
        if path is not None:
            return path
    return None


def main() -> None:
    try:
        app()
    except ChiftCliError as exc:
        emit_error(exc)
        raise SystemExit(exc.exit_code) from None


try:
    register_dynamic_commands()
except ChiftCliError as _exc:
    emit_error(_exc)
    raise SystemExit(_exc.exit_code) from None
