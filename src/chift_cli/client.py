from __future__ import annotations

import json
from typing import Any

import httpx

from .auth import get_access_token
from .config import get_api_base_url
from .errors import AuthenticationError, ChiftCliError, RetryRecommendedError
from .output import log
from .pathing import path_parameter_names
from .schema import Operation

_MISSING = object()
_PAGE_KEYS = {"items", "page", "size", "total"}
_JSON_LITERALS = {"true", "false", "null"}


def _coerce_param_value(raw: str) -> Any:
    stripped = raw.strip()
    if not stripped:
        return raw
    if stripped[0] in {"[", "{"} or stripped in _JSON_LITERALS:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return raw
    return raw


def parse_key_value(
    values: list[str] | None, *, coerce: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values or []:
        if "=" not in value:
            raise ChiftCliError("Expected KEY=VALUE.", details={"value": value})
        key, raw = value.split("=", 1)
        result[key] = _coerce_param_value(raw) if coerce else raw
    return result


def parse_json_body(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ChiftCliError("Invalid JSON body.", details={"reason": str(exc)}) from exc


def _query_parameter_names(operation: Operation) -> set[str]:
    return {parameter["name"] for parameter in operation.raw.get("parameters", []) if parameter.get("in") == "query" and "name" in parameter}


def build_request(operation: Operation, *, params: list[str] | None, body: str | None, input_values: dict[str, Any] | None = None) -> dict[str, Any]:
    all_params = parse_key_value(params, coerce=True)
    all_inputs = {**(input_values or {}), **all_params}
    query_names = _query_parameter_names(operation)
    path = operation.path
    for name in path_parameter_names(path):
        if name not in all_inputs:
            raise ChiftCliError(
                f"Missing path parameter `{name}`. Pass it with `--param {name}=...`.",
                details={"parameter": name, "path": operation.path, "example": f"--param {name}=..."},
            )
        path = path.replace("{" + name + "}", str(all_inputs.pop(name)))
    query = {
        key: value
        for key, value in all_inputs.items()
        if key in query_names
        or (key in all_params and not operation.raw.get("requestBody"))
    }
    body_inputs = {key: value for key, value in all_inputs.items() if key not in query}
    request_body = parse_json_body(body)
    if body_inputs:
        if request_body is None:
            if operation.raw.get("requestBody"):
                request_body = body_inputs
        elif isinstance(request_body, dict):
            request_body = {**request_body, **body_inputs}
        else:
            raise ChiftCliError(
                "Cannot merge KEY=VALUE inputs into a non-object --json body.",
                details={
                    "body_type": type(request_body).__name__,
                    "body_inputs": sorted(body_inputs),
                },
            )
    return {
        "method": operation.method,
        "url": f"{get_api_base_url().rstrip('/')}{path}",
        "params": query,
        "json": request_body,
    }


def _is_page_envelope(data: Any) -> bool:
    return isinstance(data, dict) and _PAGE_KEYS.issubset(data) and isinstance(data["items"], list)


def apply_fields(data: Any, fields: str | None) -> Any:
    if not fields:
        return data
    wanted = [field.strip() for field in fields.split(",") if field.strip()]
    if _is_page_envelope(data):
        return {**data, "items": [apply_fields(item, fields) for item in data["items"]]}
    if isinstance(data, list):
        return [apply_fields(item, fields) for item in data]
    if not isinstance(data, dict):
        return data
    filtered: dict[str, Any] = {}
    for field in wanted:
        value = _nested_get(data, field, default=_MISSING)
        if value is not _MISSING:
            filtered[field] = value
    return filtered


def _nested_get(data: Any, field: str, *, default: Any = None) -> Any:
    current: Any = data
    for part in field.split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return default
            if not -len(current) <= index < len(current):
                return default
            current = current[index]
        else:
            return default
    return current


def _normalize_filter_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _matches_filters(item: Any, rules: dict[str, str]) -> bool:
    if not isinstance(item, dict):
        return False
    return all(
        _normalize_filter_value(_nested_get(item, key)) == expected
        for key, expected in rules.items()
    )


def apply_filter(data: Any, filters: list[str] | None) -> Any:
    rules = parse_key_value(filters)
    if not rules:
        return data
    if _is_page_envelope(data):
        items = [item for item in data["items"] if _matches_filters(item, rules)]
        return {**data, "items": items, "total": len(items)}
    if not isinstance(data, list):
        return data
    return [item for item in data if _matches_filters(item, rules)]


def execute_operation(
    operation: Operation,
    *,
    params: list[str] | None = None,
    body: str | None = None,
    fields: str | None = None,
    filters: list[str] | None = None,
    debug: bool = False,
    input_values: dict[str, Any] | None = None,
) -> Any:
    request = build_request(operation, params=params, body=body, input_values=input_values)
    token = get_access_token(debug=debug)
    headers = {"Authorization": f"Bearer {token}"}
    log(f"{request['method']} {request['url']} params={request['params']}", debug=debug)
    try:
        response = httpx.request(
            request["method"],
            request["url"],
            params=request["params"],
            json=request["json"],
            headers=headers,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise RetryRecommendedError("Could not reach Chift API.", details={"reason": str(exc)}) from exc
    log(f"<- {response.status_code} ({len(response.content)} bytes)", debug=debug)
    if response.status_code in {401, 403}:
        raise AuthenticationError("Chift rejected the access token.", details={"status_code": response.status_code})
    if response.status_code >= 500:
        raise RetryRecommendedError("Chift API failed.", details={"status_code": response.status_code, "body": response.text})
    if response.status_code >= 400:
        raise ChiftCliError("Chift API request failed.", details={"status_code": response.status_code, "body": response.text})
    if response.status_code == 204 or not response.content:
        data: Any = None
    else:
        data = response.json()
    data = apply_filter(data, filters)
    return apply_fields(data, fields)
