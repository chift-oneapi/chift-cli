from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import httpx

from .config import get_openapi_url, schema_path, settings
from .errors import RetryRecommendedError


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
DESTRUCTIVE_METHODS = {"delete", "patch", "post", "put"}
_BACKGROUND_SCHEMA_REFRESH_LOCK = threading.Lock()
_BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS = False


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


@dataclass(frozen=True)
class OperationClassification:
    vertical: str
    entity: str


def slugify(value: str) -> str:
    value = value.replace("_", "-")
    value = re.sub(r"(?<!^)(?=[A-Z])", "-", value).lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "root"


def load_schema() -> dict[str, Any]:
    path = schema_path()
    if path.exists():
        data = json.loads(path.read_text())
        refresh_schema_in_background_if_stale()
        return data
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


def _schema_refresh_interval_seconds() -> int:
    return max(settings.schema_refresh_interval_seconds, 0)


def schema_refresh_is_due(age_seconds: int | None = None) -> bool:
    age = schema_age_seconds() if age_seconds is None else age_seconds
    interval = _schema_refresh_interval_seconds()
    return age is not None and interval > 0 and age >= interval


def _background_schema_refresh_worker(timeout: float) -> None:
    global _BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS
    try:
        update_schema(timeout=timeout)
    except Exception:
        pass
    finally:
        with _BACKGROUND_SCHEMA_REFRESH_LOCK:
            _BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS = False


def start_background_schema_refresh(*, timeout: float = 30.0) -> bool:
    global _BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS
    with _BACKGROUND_SCHEMA_REFRESH_LOCK:
        if _BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS:
            return False
        _BACKGROUND_SCHEMA_REFRESH_IN_PROGRESS = True
    thread = threading.Thread(
        target=_background_schema_refresh_worker,
        args=(timeout,),
        name="chift-schema-refresh",
        daemon=True,
    )
    thread.start()
    return True


def refresh_schema_in_background_if_stale() -> bool:
    if not schema_refresh_is_due():
        return False
    return start_background_schema_refresh()


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


def classification_from_tags(operation: dict[str, Any]) -> OperationClassification | None:
    tags = [
        slugify(tag)
        for tag in operation.get("tags") or []
        if isinstance(tag, str) and tag.strip()
    ]
    if len(tags) < 2:
        return None
    return OperationClassification(vertical=tags[0], entity=tags[1])


def classification_from_scopes(scopes: tuple[str, ...]) -> OperationClassification | None:
    candidates: dict[tuple[str, str], tuple[int, int]] = {}
    for scope in scopes:
        parts = scope.split(".")
        if len(parts) < 3 or not parts[0] or not any(parts[1:-1]):
            continue
        vertical = slugify(parts[0])
        entity = slugify(".".join(parts[1:-1]))
        count, specificity = candidates.get((vertical, entity), (0, 0))
        candidates[(vertical, entity)] = (count + 1, max(specificity, len(parts)))
    if not candidates:
        return None
    (vertical, entity), _ = sorted(
        candidates.items(),
        key=lambda item: (-item[1][0], -item[1][1], item[0][0], item[0][1]),
    )[0]
    return OperationClassification(vertical=vertical, entity=entity)


def classification_from_single_tag_and_path(path: str, operation: dict[str, Any]) -> OperationClassification | None:
    tags = [
        slugify(tag)
        for tag in operation.get("tags") or []
        if isinstance(tag, str) and tag.strip()
    ]
    if len(tags) != 1:
        return None
    return OperationClassification(vertical=tags[0], entity=entity_from_path(path))


def classification_from_path(path: str) -> OperationClassification:
    parts = [
        slugify(part)
        for part in path.strip("/").split("/")
        if part and not part.startswith("{")
    ]
    if not parts:
        return OperationClassification(vertical="root", entity="root")
    if len(parts) == 1:
        return OperationClassification(vertical=parts[0], entity=parts[0])
    if parts[0] == "consumers" and len(parts) >= 3:
        return OperationClassification(vertical=parts[1], entity=parts[-1])
    return OperationClassification(vertical=parts[0], entity=parts[-1])


def classify_operation(path: str, operation: dict[str, Any], scopes: tuple[str, ...]) -> OperationClassification:
    return (
        classification_from_scopes(scopes)
        or classification_from_tags(operation)
        or classification_from_single_tag_and_path(path, operation)
        or classification_from_path(path)
    )


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
            scopes = extract_scopes(operation)
            classification = classify_operation(path, operation, scopes)
            vertical = classification.vertical
            entity = classification.entity
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
