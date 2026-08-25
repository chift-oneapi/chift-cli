import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .config import get_openapi_url, schema_path
from .errors import RetryRecommendedError

HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put"}
DESTRUCTIVE_METHODS = {"delete", "patch", "post", "put"}
SCOPE_READ_ACTIONS = {"r", "read"}
SCOPE_ACTION_PARTS = SCOPE_READ_ACTIONS | {"w", "write"}


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


@dataclass(frozen=True)
class ScopeParts:
    prefix: str
    entity: str
    depth: int


# The URL and the scopes clip a vertical's name; the tag spells it out. Commands are
# named after the spelled-out form, so the clipped spellings map onto it, never the
# reverse.
_VERTICAL_ALIASES: dict[str, str] = {
    "pos": "point-of-sale",
    "pms": "property-management-system",
    "commerce": "e-commerce",
}


def slugify(value: str) -> str:
    value = value.replace("_", "-")
    value = re.sub(r"(?<!^)(?=[A-Z])", "-", value).lower()
    return re.sub(r"[^a-z0-9-]+", "-", value)


def load_schema() -> dict[str, Any]:
    path = schema_path()
    if path.exists():
        return json.loads(path.read_text())
    _, data = update_schema()
    return data


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
        raise RetryRecommendedError(
            "Could not update the Chift OpenAPI schema.",
            details={"url": url, "reason": str(exc)},
        ) from exc
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


def is_oneapi_code(part: str) -> bool:
    return part.isdigit()


def has_read_scope(scopes: tuple[str, ...]) -> bool:
    return any(scope.split(".")[-1] in SCOPE_READ_ACTIONS for scope in scopes)


def canonical_vertical(value: str) -> str:
    """Reduce any spelling of a vertical to the one name its commands live under.

    A vertical is named three different ways: the scope prefix and the URL agree
    on a short form (`pms`), while the tag is display prose that slugifies to
    something longer. Any two of them left unreconciled would split one
    vertical's commands across two groups in the help output.
    """
    slug = re.sub(r"-{2,}", "-", value).strip("-")
    return _VERTICAL_ALIASES.get(slug, slug)


def classification_from_tags(
    operation: dict[str, Any],
) -> OperationClassification | None:
    tags = [slugify(tag) for tag in operation.get("tags") or [] if isinstance(tag, str) and tag.strip()]
    if len(tags) < 2:
        return None
    return OperationClassification(vertical=canonical_vertical(tags[0]), entity=tags[1])


def classification_from_single_tag_and_path(path: str, operation: dict[str, Any]) -> OperationClassification | None:
    tags = [slugify(tag) for tag in operation.get("tags") or [] if isinstance(tag, str) and tag.strip()]
    if len(tags) != 1:
        return None
    return OperationClassification(vertical=canonical_vertical(tags[0]), entity=entity_from_path(path))


def classification_from_path(path: str) -> OperationClassification:
    """Last-resort classification from the URL path alone.

    `/consumers/{id}/accounting/accounts` is consumer-scoped, so the segment
    after the consumer id is the real vertical; otherwise the first segment is
    the vertical and the last is the entity.
    """
    parts = [slugify(part) for part in path.strip("/").split("/") if part and not part.startswith("{")]
    if not parts:
        return OperationClassification(vertical="root", entity="root")
    if len(parts) == 1:
        return OperationClassification(vertical=canonical_vertical(parts[0]), entity=parts[0])
    if parts[0] == "consumers" and len(parts) >= 3:
        return OperationClassification(vertical=canonical_vertical(parts[1]), entity=parts[-1])
    return OperationClassification(vertical=canonical_vertical(parts[0]), entity=parts[-1])


def split_scope(scope: str) -> ScopeParts | None:
    """Split a scope into the prefix naming its vertical and the entity it grants.

    The prefix is either a vertical name or the numeric API code standing in for
    one. A trailing action belongs to neither, and a scope that grants a whole
    vertical rather than an entity has nothing to contribute.
    """
    parts = scope.split(".")
    if len(parts) < 2 or not parts[0]:
        return None
    entity_parts = parts[1:-1] if parts[-1] in SCOPE_ACTION_PARTS else parts[1:]
    if not entity_parts or not any(entity_parts):
        return None
    return ScopeParts(prefix=parts[0], entity=slugify(".".join(entity_parts)), depth=len(entity_parts))


def classification_from_scopes(path: str, scopes: tuple[str, ...]) -> OperationClassification | None:
    """Derive (vertical, entity) from the scopes an operation declares.

    A named prefix (`accounting.invoices.read`) is the vertical. The numeric API
    code that replaces it (`200.invoices.r`) is nothing a user would type, so the
    name comes from the URL, which spells it the same way the named scopes do.
    Named prefixes win while the API sends both forms, and reading both through
    one rule is what keeps a command's name stable when the named form goes away.

    Ranking the entities by how many scopes name them collapses the two- and
    three-part scopes for one entity together. Several prefixes mean the endpoint
    is reachable from several verticals (`accounting.datalab`, `pos.datalab`,
    ...) with none to single out, so we give up and let a less trusted signal
    classify it.
    """
    parsed = [parts for scope in scopes if (parts := split_scope(scope)) is not None]
    named = [parts for parts in parsed if not is_oneapi_code(parts.prefix)]
    chosen = named or parsed
    if not chosen or len({parts.prefix for parts in chosen}) != 1:
        return None
    entities: dict[str, tuple[int, int]] = {}
    for parts in chosen:
        count, depth = entities.get(parts.entity, (0, 0))
        entities[parts.entity] = (count + 1, max(depth, parts.depth))
    return OperationClassification(
        vertical=canonical_vertical(slugify(chosen[0].prefix)) if named else classification_from_path(path).vertical,
        entity=min(entities, key=lambda name: (-entities[name][0], -entities[name][1], name)),
    )


def classify_operation(path: str, operation: dict[str, Any], scopes: tuple[str, ...]) -> OperationClassification:
    """Pick a (vertical, entity) for an operation, most-trusted source first."""
    return (
        classification_from_scopes(path, scopes)
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


def resolve_refs_deep(schema: Any, document: dict[str, Any], _seen: frozenset[str] | None = None) -> Any:
    """Inline every local `$ref` in a schema. `_seen` breaks recursive refs."""
    if not isinstance(schema, dict):
        return schema
    seen = _seen or frozenset()
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/") and ref not in seen:
        resolved = resolve_ref(schema, document)
        if resolved is not schema:
            return resolve_refs_deep(resolved, document, seen | {ref})
        return schema
    result = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            result[key] = resolve_refs_deep(value, document, seen)
        elif isinstance(value, list):
            result[key] = [
                resolve_refs_deep(item, document, seen) if isinstance(item, dict) else item for item in value
            ]
        else:
            result[key] = value
    return result


def response_schema(operation: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses") or {}
    for status_code in ("200", "201", "202"):
        content = responses.get(status_code, {}).get("content") or {}
        schema = content.get("application/json", {}).get("schema")
        if isinstance(schema, dict):
            return schema
    return {}


def response_is_collection(operation: dict[str, Any], document: dict[str, Any]) -> bool:
    """True if the success response is a bare array or a paginated `ChiftPage`.

    Used to name a read command `list` rather than `get`.
    """
    schema = resolve_ref(response_schema(operation), document)
    if schema.get("type") == "array":
        return True
    properties = schema.get("properties") or {}
    page_fields = {"items", "page", "size", "total"}
    return page_fields.issubset(properties) or page_fields.issubset(set(schema.get("required") or []))


def command_name(
    method: str,
    path: str,
    operation: dict[str, Any],
    scopes: tuple[str, ...],
    document: dict[str, Any],
    used: set[str],
) -> str:
    """Name a command from its verb (list/get/create/update/replace/delete).

    `used` tracks names already taken within the same entity; on a collision we
    fall back to a slugified summary, suffixed `-2`, `-3`, … until unique.
    """
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


def tree(
    schema: dict[str, Any] | None = None,
) -> dict[str, dict[str, list[dict[str, str]]]]:
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
