import pytest

pytest.importorskip("textual")

from agent_cli.auth_ui import AuthenticationApp
from textual.widgets import Button, Static


class FakeAuth:
    def __init__(self):
        self.verification_callback = None

    def sign_in(self):
        raise AssertionError("the authentication screen should not sign in on mount")

    def sign_up(self):
        raise AssertionError("the authentication screen should not sign up on mount")


@pytest.mark.asyncio
async def test_auth_screen_exposes_browser_sign_in_and_sign_up_actions():
    app = AuthenticationApp(FakeAuth())

    async with app.run_test():
        assert isinstance(app.query_one("#sign-in"), Button)
        assert isinstance(app.query_one("#sign-up"), Button)
        assert isinstance(app.query_one("#account"), Button)
        assert isinstance(app.query_one("#logout"), Button)
        assert isinstance(app.query_one("#auth-status"), Static)
