from __future__ import annotations

from typer.testing import CliRunner

from chift_cli import config
from chift_cli.auth_form import AuthFormValues
from chift_cli.cli import app
from chift_cli.config import Token, load_api_key_credentials
from chift_cli.errors import AuthenticationError


runner = CliRunner()


def test_auth_setup_uses_terminal_form_for_missing_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "config_dir", str(tmp_path))

    def fake_fetch_token(credentials, *, debug=False):
        return Token(access_token="token", expires_on=123)

    monkeypatch.setattr("chift_cli.cli.fetch_token", fake_fetch_token)
    monkeypatch.setattr(
        "chift_cli.cli.prompt_auth_credentials",
        lambda **kwargs: AuthFormValues(account_id="acct", client_id="client", client_secret="secret"),
    )
    result = runner.invoke(app, ["auth", "setup"])

    assert result.exit_code == 0
    assert result.stdout == "Chift authentication configured.\n"
    credentials = load_api_key_credentials()
    assert credentials is not None
    assert credentials.account_id == "acct"
    assert credentials.client_id == "client"
    assert credentials.client_secret == "secret"


def test_auth_setup_with_flags_prints_success_message(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "config_dir", str(tmp_path))

    def fake_fetch_token(credentials, *, debug=False):
        return Token(access_token="token", token_type="bearer", expires_on=123)

    monkeypatch.setattr("chift_cli.cli.fetch_token", fake_fetch_token)
    result = runner.invoke(
        app,
        [
            "auth",
            "setup",
            "--account-id",
            "acct",
            "--client-id",
            "client",
            "--client-secret",
            "secret",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "Chift authentication configured.\n"


def test_auth_setup_errors_are_plain_text(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "config_dir", str(tmp_path))

    def fake_fetch_token(credentials, *, debug=False):
        raise AuthenticationError("Invalid Chift credentials.")

    monkeypatch.setattr("chift_cli.cli.fetch_token", fake_fetch_token)
    result = runner.invoke(
        app,
        [
            "auth",
            "setup",
            "--account-id",
            "acct",
            "--client-id",
            "client",
            "--client-secret",
            "secret",
        ],
    )

    assert result.exit_code == 3
    assert result.stdout == ""
    assert result.stderr == "Invalid Chift credentials.\n"
