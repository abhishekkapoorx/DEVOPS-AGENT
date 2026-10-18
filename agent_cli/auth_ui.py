"""Minimal Textual sign-in/sign-up surface backed by the auth client seam."""

from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Center, Vertical
from textual.widgets import Button, Footer, Header, Static

from .auth import DeviceLogin
from .auth import TokenResponse


class AuthenticationApp(App[TokenResponse | None]):
    TITLE = "DevOps Agent"
    SUB_TITLE = "Sign in or create an account"
    CSS = """
    Screen { align: center middle; }
    #auth-panel { width: 64; height: auto; padding: 2 4; border: round $accent; }
    #auth-status { height: auto; min-height: 3; margin-bottom: 1; }
    #auth-panel Button { width: 100%; margin-bottom: 1; }
    """

    def __init__(self, auth: DeviceLogin) -> None:
        super().__init__()
        self.auth = auth
        self.auth.verification_callback = self._show_verification

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(id="auth-panel"):
                yield Static("Choose how to continue.", id="auth-status")
                yield Button("Sign in", id="sign-in", variant="primary")
                yield Button("Create account", id="sign-up")
                yield Button("Current account", id="account")
                yield Button("Sign out", id="logout", variant="warning")
                yield Button("Quit", id="quit")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sign-in":
            self.handle_action("signin")
        elif event.button.id == "sign-up":
            self.handle_action("signup")
        elif event.button.id == "account":
            self.handle_action("account")
        elif event.button.id == "logout":
            self.handle_action("logout")
        elif event.button.id == "quit":
            self.exit(None)

    @work(thread=True, exclusive=True, exit_on_error=False)
    def handle_action(self, action: str) -> None:
        try:
            if action in {"signin", "signup"}:
                self.call_from_thread(self._set_status, "Opening your browser for approval…")
                result = self.auth.sign_up() if action == "signup" else self.auth.sign_in()
                self.call_from_thread(self.exit, result)
            elif action == "account":
                tokens = self.auth.restore()
                if tokens is None:
                    self.call_from_thread(self._set_status, "Not signed in.")
                else:
                    user = self.auth.current_user(tokens.access_token)
                    self.call_from_thread(self._set_status, f"Signed in as {user['user_id']}.")
            elif action == "logout":
                self.auth.logout()
                self.call_from_thread(self._set_status, "Signed out.")
        except Exception as error:
            self.call_from_thread(self._set_status, f"Authentication failed: {error}")

    def _show_verification(self, url: str, code: str) -> None:
        self.call_from_thread(
            self._set_status,
            f"Finish signing in at {url}\nEnter code: {code}",
        )

    def _set_status(self, value: str) -> None:
        self.query_one("#auth-status", Static).update(value)


def run_auth_ui(auth: DeviceLogin) -> TokenResponse | None:
    """Run the Textual authentication screen and return the approved tokens."""
    return AuthenticationApp(auth).run()


__all__ = ["AuthenticationApp", "run_auth_ui"]
