import httpx
import pytest

from chift_cli.auth import fetch_token
from chift_cli.config import ApiKeyCredentials
from chift_cli.errors import AuthenticationError, RetryRecommendedError


def test_fetch_token_uses_chift_error_detail(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(401, json={"detail": "Invalid client secret."})

    monkeypatch.setattr("chift_cli.auth.httpx.post", fake_post)

    with pytest.raises(AuthenticationError) as exc_info:
        fetch_token(ApiKeyCredentials(account_id="acct", client_id="client", client_secret="secret"))

    assert exc_info.value.message == "Could not authenticate with Chift. reason: Invalid client secret."


def test_fetch_token_formats_validation_details(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(
            422,
            json={"detail": [{"loc": ["body", "accountId"], "msg": "Field required", "type": "missing"}]},
        )

    monkeypatch.setattr("chift_cli.auth.httpx.post", fake_post)

    with pytest.raises(AuthenticationError) as exc_info:
        fetch_token(ApiKeyCredentials(account_id="", client_id="client", client_secret="secret"))

    assert exc_info.value.message == "Could not authenticate with Chift. reason: Field required"


def test_fetch_token_prefers_validation_detail_over_generic_message(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(
            422,
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

    monkeypatch.setattr("chift_cli.auth.httpx.post", fake_post)

    with pytest.raises(AuthenticationError) as exc_info:
        fetch_token(ApiKeyCredentials(account_id="erge", client_id="client", client_secret="secret"))

    assert exc_info.value.message == "Could not authenticate with Chift. reason: Input should be a valid UUID"


def test_fetch_token_uses_server_error_body(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(503, json={"message": "Token service unavailable."})

    monkeypatch.setattr("chift_cli.auth.httpx.post", fake_post)

    with pytest.raises(RetryRecommendedError) as exc_info:
        fetch_token(ApiKeyCredentials(account_id="acct", client_id="client", client_secret="secret"))

    assert exc_info.value.message == "Could not authenticate with Chift. reason: Token service unavailable."
