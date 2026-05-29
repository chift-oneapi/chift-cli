from dataclasses import dataclass

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea


@dataclass(frozen=True)
class AuthFormValues:
    account_id: str
    client_id: str
    client_secret: str


def normalize_auth_form_values(
    *,
    account_id: str,
    client_id: str,
    client_secret: str,
) -> AuthFormValues:
    return AuthFormValues(
        account_id=account_id.strip(),
        client_id=client_id.strip(),
        client_secret=client_secret.strip(),
    )


def _label(title: str, helper: str) -> HSplit:
    return HSplit(
        [
            Window(FormattedTextControl([("class:accent", "▌ "), ("class:label", title)]), height=1),
            Window(FormattedTextControl([("", "  "), ("class:helper", helper)]), height=1),
        ]
    )


def _field(*, password: bool = False) -> TextArea:
    return TextArea(
        height=1,
        multiline=False,
        password=password,
        prompt=[("", "  "), ("class:prompt", "› ")],
    )


def prompt_auth_credentials(
    *,
    account_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> AuthFormValues:
    account = _field()
    client = _field()
    secret = _field(password=True)
    account.text = account_id or ""
    client.text = client_id or ""
    secret.text = client_secret or ""
    fields = [account, client, secret]

    bindings = KeyBindings()

    def focus_next() -> None:
        current = application.layout.current_window
        for index, field in enumerate(fields):
            if field.window == current:
                application.layout.focus(fields[(index + 1) % len(fields)])
                return
        application.layout.focus(fields[0])

    def focus_previous() -> None:
        current = application.layout.current_window
        for index, field in enumerate(fields):
            if field.window == current:
                application.layout.focus(fields[(index - 1) % len(fields)])
                return
        application.layout.focus(fields[-1])

    def missing_field() -> TextArea | None:
        for field in fields:
            if not field.text.strip():
                return field
        return None

    def submit() -> None:
        missing = missing_field()
        if missing:
            application.layout.focus(missing)
            return
        application.exit(
            result=normalize_auth_form_values(
                account_id=account.text,
                client_id=client.text,
                client_secret=secret.text,
            )
        )

    @bindings.add("tab", eager=True)
    def _(event) -> None:
        focus_next()

    @bindings.add("s-tab", eager=True)
    def _(event) -> None:
        focus_previous()

    @bindings.add("enter", eager=True)
    def _(event) -> None:
        submit()

    @bindings.add("c-c")
    def _(event) -> None:
        event.app.exit(exception=KeyboardInterrupt)

    header = HSplit(
        [
            Window(
                FormattedTextControl(
                    [
                        ("class:title.brand", "chift"),
                        ("class:title", " auth setup"),
                        ("class:title.dim", "  configure API credentials"),
                    ]
                ),
                height=1,
            ),
            Window(FormattedTextControl([("class:rule", "━" * 44)]), height=1),
            Window(
                FormattedTextControl(
                    [
                        ("class:helper", "Get an API key: "),
                        ("class:link", "https://chift.app/api-keys"),
                    ]
                ),
                height=1,
            ),
        ]
    )
    root = HSplit(
        [
            header,
            Window(height=1),
            _label("Account ID", "Your Chift account ID"),
            account,
            Window(height=Dimension.exact(1)),
            _label("Client ID", "Your Chift client ID"),
            client,
            Window(height=Dimension.exact(1)),
            _label("Client Secret", "Your Chift client secret"),
            secret,
            Window(height=1),
            Window(FormattedTextControl([("class:hint", "  Tab changes field · Enter saves")]), height=1),
        ]
    )
    style = Style.from_dict(
        {
            "title": "#F6F6F6 bold",
            "title.brand": "#04C28F bold",
            "title.dim": "#88AAFB",
            "rule": "#052B2E",
            "accent": "#04C28F",
            "label": "#F6F6F6 bold",
            "helper": "#F6F6F6",
            "link": "#88AAFB underline",
            "prompt": "#88AAFB bold",
            "hint": "#88AAFB",
        }
    )
    application: Application[AuthFormValues] = Application(
        layout=Layout(root, focused_element=account),
        key_bindings=bindings,
        style=style,
        full_screen=False,
    )
    return application.run()
