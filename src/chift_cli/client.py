from __future__ import annotations

import json
from typing import Any

import httpx

from .auth import get_access_token
from .config import get_api_base_url
from .errors import AuthenticationError, ChiftCliError, RetryRecommendedError
from .schema import Operation


def parse_key_value(values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ChiftCliError("Expected KEY=VALUE.", details={"value": value})
        key, raw = value.split("=", 1)
        result[key] = raw
    return result


def parse_json_body(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ChiftCliError("Invalid JSON body.", details={"reason": str(exc)}) from exc


def _path_parameter_names(path: str) -> list[str]:
    return [part[1:-1] for part in path.split("/") if part.startswith("{") and part.endswith("}")]


def _query_parameter_names(operation: Operation) -> set[str]:
    return {parameter["name"] for parameter in operation.raw.get("parameters", []) if parameter.get("in") == "query" and "name" in parameter}


def build_request(operation: Operation, *, params: list[str] | None, body: str | None, input_values: dict[str, Any] | None = None) -> dict[str, Any]:
    all_params = parse_key_value(params)
    all_inputs = {**(input_values or {}), **all_params}
    query_names = _query_parameter_names(operation)
    path = operation.path
    for name in _path_parameter_names(path):
        if name not in all_inputs:
            raise ChiftCliError(
                f"Missing path parameter `{name}`. Pass it with `--param {name}=...`.",
                details={"parameter": name, "path": operation.path, "example": f"--param {name}=..."},
            )
        path = path.replace("{" + name + "}", str(all_inputs.pop(name)))
    query = {key: value for key, value in all_inputs.items() if key in query_names or key in all_params and not operation.raw.get("requestBody")}
    body_inputs = {key: value for key, value in all_inputs.items() if key not in query}
    request_body = parse_json_body(body)
    if body_inputs and isinstance(request_body, dict):
        request_body = {**request_body, **body_inputs}
    elif body_inputs and operation.raw.get("requestBody"):
        request_body = body_inputs
    return {
        "method": operation.method,
        "url": f"{get_api_base_url().rstrip('/')}{path}",
        "params": query,
        "json": request_body,
    }


def apply_fields(data: Any, fields: str | None) -> Any:
    if not fields:
        return data
    wanted = [field.strip() for field in fields.split(",") if field.strip()]
    if isinstance(data, list):
        return [apply_fields(item, fields) for item in data]
    if not isinstance(data, dict):
        return data
    return {field: _nested_get(data, field) for field in wanted if _nested_get(data, field) is not None}


def _nested_get(data: dict[str, Any], field: str) -> Any:
    current: Any = data
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def apply_filter(data: Any, filters: list[str] | None) -> Any:
    rules = parse_key_value(filters)
    if not rules or not isinstance(data, list):
        return data
    return [item for item in data if isinstance(item, dict) and all(str(_nested_get(item, key)) == value for key, value in rules.items())]


def execute_operation(
    operation: Operation,
    *,
    params: list[str] | None = None,
    body: str | None = None,
    fields: str | None = None,
    filters: list[str] | None = None,
    dry_run: bool = False,
    debug: bool = False,
    input_values: dict[str, Any] | None = None,
) -> Any:
    request = build_request(operation, params=params, body=body, input_values=input_values)
    if dry_run:
        scrubbed = dict(request)
        scrubbed["headers"] = {"authorization": "Bearer ***"}
        return scrubbed
    token = get_access_token(debug=debug)
    headers = {"Authorization": f"Bearer {token}"}
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
