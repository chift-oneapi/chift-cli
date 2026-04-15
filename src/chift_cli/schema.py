from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import httpx

from .config import get_openapi_url, schema_path
from .errors import RetryRecommendedError


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
DESTRUCTIVE_METHODS = {"delete", "patch", "post", "put"}


BUILTIN_SCHEMA: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Chift API", "version": "1.0.0"},
    "servers": [{"url": "https://api.chift.eu"}],
    "paths": {
        "/token": {
            "post": {
                "tags": ["General"],
                "summary": "Get access token",
                "operationId": "generate_access_token_token_post",
                "security": [],
            }
        },
        "/consumers": {
            "get": {
                "tags": ["Consumers"],
                "summary": "Get consumers",
                "operationId": "consumers_get_consumers",
                "parameters": [
                    {"name": "search", "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "internal_reference", "in": "query", "required": False, "schema": {"type": "string"}},
                ],
            },
            "post": {
                "tags": ["Consumers"],
                "summary": "Create new consumer",
                "operationId": "consumers_create_consumer",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PostConsumerItem"}}}},
            },
        },
        "/consumers/{consumer_id}": {
            "get": {
                "tags": ["Consumers"],
                "summary": "Get one consumer",
                "operationId": "consumers_get_consumer",
                "parameters": [{"name": "consumer_id", "in": "path", "required": True, "schema": {"type": "string"}}],
            },
            "delete": {
                "tags": ["Consumers"],
                "summary": "Delete one consumer",
                "operationId": "consumers_delete_consumer",
                "parameters": [{"name": "consumer_id", "in": "path", "required": True, "schema": {"type": "string"}}],
            },
        },
    },
    "components": {"schemas": {}},
}


@dataclass(frozen=True)
class Operation:
    vertical: str
    entity: str
    command: str
    method: str
    path: str
    operation_id: str
    summary: str
    scopes: tuple[str, ...]
    raw: dict[str, Any]
    components: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def slugify(value: str) -> str:
    value = value.replace("_", "-")
    value = re.sub(r"(?<!^)(?=[A-Z])", "-", value).lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "root"


def load_schema() -> dict[str, Any]:
    path = schema_path()
    if path.exists():
        return json.loads(path.read_text())
    try:
        _, data = update_schema()
        return data
    except RetryRecommendedError:
        pass
    return BUILTIN_SCHEMA


def save_schema(schema: dict[str, Any], path: Path | None = None) -> Path:
    target = path or schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    return target


def update_schema(*, timeout: float = 30.0) -> tuple[Path, dict[str, Any]]:
    url = get_openapi_url()
    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RetryRecommendedError("Could not update the Chift OpenAPI schema.", details={"url": url, "reason": str(exc)}) from exc
    data = response.json()
    return save_schema(data), data


def schema_age_seconds() -> int | None:
    path = schema_path()
    if not path.exists():
        return None
    return int(time.time() - path.stat().st_mtime)


def entity_from_path(path: str) -> str:
    parts = [part for part in path.strip("/").split("/") if part and not part.startswith("{")]
    if not parts:
        return "root"
    return slugify(parts[-1])


def extract_scopes(operation: dict[str, Any]) -> tuple[str, ...]:
    scopes: set[str] = set()
    security = operation.get("security") or []
    for item in security:
        for values in item.values():
            if isinstance(values, list):
                scopes.update(value for value in values if isinstance(value, str))
    return tuple(sorted(scopes))


def has_read_scope(scopes: tuple[str, ...]) -> bool:
    return any(scope.split(".")[-1] == "read" for scope in scopes)


def entity_from_scopes(vertical: str, scopes: tuple[str, ...]) -> str | None:
    candidates: list[tuple[int, str]] = []
    for scope in scopes:
        parts = scope.split(".")
        if len(parts) < 2:
            continue
        entity = parts[-2] if len(parts) > 2 else parts[-1]
        if slugify(entity) == vertical:
            continue
        candidates.append((len(parts), slugify(entity)))
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][1]


def entity_name(path: str, vertical: str, scopes: tuple[str, ...]) -> str:
    return entity_from_scopes(vertical, scopes) or entity_from_path(path)


def resolve_ref(schema: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return schema
    current: Any = document
    for part in ref.removeprefix("#/").split("/"):
        if not isinstance(current, dict):
            return schema
        current = current.get(part)
    return current if isinstance(current, dict) else schema


def response_schema(operation: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses") or {}
    for status_code in ("200", "201", "202"):
        content = responses.get(status_code, {}).get("content") or {}
        schema = content.get("application/json", {}).get("schema")
        if isinstance(schema, dict):
            return schema
    return {}


def response_is_collection(operation: dict[str, Any], document: dict[str, Any]) -> bool:
    schema = resolve_ref(response_schema(operation), document)
    if schema.get("type") == "array":
        return True
    properties = schema.get("properties") or {}
    page_fields = {"items", "page", "size", "total"}
    return page_fields.issubset(properties) or page_fields.issubset(set(schema.get("required") or []))


def command_name(method: str, path: str, operation: dict[str, Any], scopes: tuple[str, ...], document: dict[str, Any], used: set[str]) -> str:
    if has_read_scope(scopes):
        base = "list" if response_is_collection(operation, document) else "get"
    elif method == "get":
        base = "list" if response_is_collection(operation, document) else "get"
    elif method == "post":
        base = "create"
    elif method == "patch":
        base = "update"
    elif method == "put":
        base = "replace"
    elif method == "delete":
        base = "delete"
    else:
        base = method
    if base not in used:
        used.add(base)
        return base
    summary = slugify(operation.get("summary") or operation.get("operationId") or method)
    name = summary
    index = 2
    while name in used:
        name = f"{summary}-{index}"
        index += 1
    used.add(name)
    return name


def iter_operations(schema: dict[str, Any] | None = None) -> list[Operation]:
    data = schema or load_schema()
    operations: list[Operation] = []
    used: dict[tuple[str, str], set[str]] = {}
    for path, methods in sorted(data.get("paths", {}).items()):
        for method, operation in sorted(methods.items()):
            if method not in HTTP_METHODS:
                continue
            vertical = slugify((operation.get("tags") or ["general"])[0])
            scopes = extract_scopes(operation)
            entity = entity_name(path, vertical, scopes)
            key = (vertical, entity)
            used.setdefault(key, set())
            command = command_name(method, path, operation, scopes, data, used[key])
            operations.append(
                Operation(
                    vertical=vertical,
                    entity=entity,
                    command=command,
                    method=method.upper(),
                    path=path,
                    operation_id=operation.get("operationId", ""),
                    summary=operation.get("summary", ""),
                    scopes=scopes,
                    raw=operation,
                    components=data.get("components", {}),
                )
            )
    return operations


def tree(schema: dict[str, Any] | None = None) -> dict[str, dict[str, list[dict[str, str]]]]:
    result: dict[str, dict[str, list[dict[str, str]]]] = {}
    for operation in iter_operations(schema):
        result.setdefault(operation.vertical, {}).setdefault(operation.entity, []).append(
            {
                "command": operation.command,
                "method": operation.method,
                "path": operation.path,
                "summary": operation.summary,
                "operation_id": operation.operation_id,
                "scopes": list(operation.scopes),
            }
        )
    return result


def find_operation(vertical: str, entity: str, command: str, schema: dict[str, Any] | None = None) -> Operation | None:
    for operation in iter_operations(schema):
        if operation.vertical == vertical and operation.entity == entity and operation.command == command:
            return operation
    return None


def search_schema(query: str, schema: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    needle = query.lower()
    data = schema or load_schema()
    matches: list[dict[str, Any]] = []
    for operation in iter_operations(data):
        haystack = json.dumps(operation.raw, sort_keys=True).lower()
        if needle in haystack or needle in operation.path.lower() or needle in operation.summary.lower():
            matches.append(
                {
                    "vertical": operation.vertical,
                    "entity": operation.entity,
                    "command": operation.command,
                    "method": operation.method,
                    "path": operation.path,
                    "summary": operation.summary,
                    "operation_id": operation.operation_id,
                    "scopes": list(operation.scopes),
                }
            )
    return matches


def filter_by_scopes(operations: Iterable[Operation], scopes: set[str] | None) -> list[Operation]:
    if not scopes:
        return list(operations)
    result = []
    for operation in operations:
        needed = set(operation.scopes)
        if not needed or needed & scopes:
            result.append(operation)
    return result
