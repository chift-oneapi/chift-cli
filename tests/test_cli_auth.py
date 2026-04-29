from __future__ import annotations

from typer.testing import CliRunner

from chift_cli import config
from chift_cli.auth_form import AuthFormValues, normalize_auth_form_values
from chift_cli.cli import app
from chift_cli.config import (
    ApiKeyCredentials,
    Token,
    load_api_key_credentials,
    save_api_key_credentials,
)
from chift_cli.errors import AuthenticationError


runner = CliRunner()


def test_auth_help_describes_commands() -> None:
    result = runner.invoke(app, ["auth", "--help"])

    assert result.exit_code == 0
    assert "Configure and validate Chift API credentials." in result.stdout
    assert "Save API credentials and verify them by fetching a token." in result.stdout
    assert "Validate saved API credentials by fetching a fresh token." in result.stdout


def test_auth_setup_help_links_to_api_keys() -> None:
    result = runner.invoke(app, ["auth", "setup", "--help"])
    normalized_stdout = " ".join(result.stdout.split())

    assert result.exit_code == 0
    assert "Get an API key at https://chift.app/api-keys." in normalized_stdout


def test_auth_check_help_describes_fresh_token_validation() -> None:
    result = runner.invoke(app, ["auth", "check", "--help"])
    normalized_stdout = " ".join(result.stdout.split())

    assert result.exit_code == 0
    assert (
        "Validate saved API credentials by fetching a fresh token."
        in normalized_stdout
    )
    assert "instead of only inspecting the local token cache" in normalized_stdout


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


def test_auth_setup_does_not_save_credentials_when_validation_fails(
    monkeypatch, tmp_path
) -> None:
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
            "bad",
            "--client-secret",
            "bad",
        ],
    )

    assert result.exit_code == 3
    assert load_api_key_credentials() is None


def test_auth_check_refreshes_token_with_saved_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "config_dir", str(tmp_path))
    save_api_key_credentials(
        ApiKeyCredentials(
            account_id="acct",
            client_id="client",
            client_secret="secret",
        )
    )
    checked: dict[str, str] = {}

    def fake_fetch_token(credentials, *, debug=False):
        checked["account_id"] = credentials.account_id
        checked["client_id"] = credentials.client_id
        checked["client_secret"] = credentials.client_secret
        return Token(access_token="token", token_type="bearer", expires_on=123)

    monkeypatch.setattr("chift_cli.cli.fetch_token", fake_fetch_token)

    result = runner.invoke(app, ["auth", "check"])

    assert result.exit_code == 0
    assert result.stdout == "Chift authentication valid.\n"
    assert checked == {
        "account_id": "acct",
        "client_id": "client",
        "client_secret": "secret",
    }


def test_auth_check_requires_saved_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config.settings, "config_dir", str(tmp_path))

    result = runner.invoke(app, ["auth", "check"])

    assert result.exit_code == 3
    assert result.stdout == ""
    assert result.stderr == "No API credentials found. Run `chift auth setup` first.\n"


def test_auth_form_normalizes_all_fields() -> None:
    assert normalize_auth_form_values(
        account_id=" acct ",
        client_id=" client ",
        client_secret=" secret \n",
    ) == AuthFormValues(
        account_id="acct",
        client_id="client",
        client_secret="secret",
    )
