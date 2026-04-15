from __future__ import annotations

import json
import sys
from typing import Any, Literal

import typer
import yaml

from .errors import ChiftCliError


OutputFormat = Literal["json", "yaml"]


def emit(data: Any, output: OutputFormat = "json") -> None:
    if output == "json":
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
        return
    typer.echo(yaml.safe_dump(data, sort_keys=True))


def log(message: str, *, debug: bool = False) -> None:
    if debug:
        typer.echo(message, err=True)


def emit_error(error: ChiftCliError, output: OutputFormat = "json") -> None:
    payload = {
        "error": {
            "message": error.message,
            "type": error.__class__.__name__,
            "details": error.details,
        }
    }
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
    else:
        print(yaml.safe_dump(payload, sort_keys=True), file=sys.stderr)

