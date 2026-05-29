import pytest
from pytest_httpx import HTTPXMock

from chift_cli.auth import fetch_token
from chift_cli.config import ApiKeyCredentials
from chift_cli.errors import AuthenticationError, RetryRecommendedError

TOKEN_URL = "https://api.chift.eu/token"


def test_fetch_token_uses_chift_error_detail(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, status_code=401, json={"detail": "Invalid client secret."})

    with pytest.raises(AuthenticationError, match="Could not authenticate with Chift. reason: Invalid client secret."):
        fetch_token(ApiKeyCredentials(account_id="acct", client_id="client", client_secret="secret"))


def test_fetch_token_formats_validation_details(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=TOKEN_URL,
        status_code=422,
        json={"detail": [{"loc": ["body", "accountId"], "msg": "Field required", "type": "missing"}]},
    )

    with pytest.raises(AuthenticationError, match="Could not authenticate with Chift. reason: Field required"):
        fetch_token(ApiKeyCredentials(account_id="", client_id="client", client_secret="secret"))


def test_fetch_token_prefers_validation_detail_over_generic_message(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=TOKEN_URL,
        status_code=422,
        json={
            "message": "Validation error",
            "detail": [
                {
                    "loc": ["body", "accountId"],
                    "msg": "Input should be a valid UUID",
                    "type": "uuid_parsing",
                }
            ],
        },
    )

    with pytest.raises(
        AuthenticationError, match="Could not authenticate with Chift. reason: Input should be a valid UUID"
    ):
        fetch_token(ApiKeyCredentials(account_id="erge", client_id="client", client_secret="secret"))


def test_fetch_token_uses_server_error_body(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=TOKEN_URL, status_code=503, json={"message": "Token service unavailable."})

    with pytest.raises(
        RetryRecommendedError, match="Could not authenticate with Chift. reason: Token service unavailable."
    ):
        fetch_token(ApiKeyCredentials(account_id="acct", client_id="client", client_secret="secret"))
