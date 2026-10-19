import pytest
from agent_cli.auth import TokenResponse
from agent_cli.textual_app import TextualAgentApp


class FakeAuth:
    def __init__(self, tokens=None):
        self.tokens = tokens
        self.verification_callback = lambda *_: None
        self.logged_out = False

    def restore(self):
        return self.tokens

    def sign_in(self):
        self.tokens = TokenResponse(
            access_token="access", refresh_token="refresh", expires_in=60, user_id="user-1"
        )
        return self.tokens

    def sign_up(self):
        return self.sign_in()

    def logout(self):
        self.logged_out = True
        self.tokens = None


class FakeClient:
    def __init__(self):
        self.created = []
        self.sent = []

    def list_conversations(self):
        return [{"id": "conversation-1", "title": "Existing"}]

    def create_conversation(self, title="New conversation"):
        conversation = {"id": "conversation-2", "title": title}
        self.created.append(conversation)
        return conversation

    def list_messages(self, conversation_id):
        return [{"role": "user", "content": f"history for {conversation_id}"}]

    def ask(self, message, *, conversation_id=None, on_event=None):
        self.sent.append((message, conversation_id))
        if on_event:
            on_event({"type": "agent_message", "message": "streamed"})
        return {"message": "answer"}


def token():
    return TokenResponse(
        access_token="access", refresh_token="refresh", expires_in=60, user_id="user-1"
    )


@pytest.mark.asyncio
async def test_textual_conversation_app_signs_in_creates_chat_and_sends_message():
    auth = FakeAuth()
    client = FakeClient()
    app = TextualAgentApp(auth, lambda _tokens: client)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#sign-up")
        await pilot.pause()
        await pilot.click("#new-conversation")
        await pilot.pause(0.1)
        assert app.selected_conversation_id == "conversation-2"
        app.query_one("#message").value = "check status"
        clicked = await pilot.click("#send")
        await pilot.pause(0.1)

    assert client.created == [{"id": "conversation-2", "title": "New conversation"}]
    assert client.sent == [("check status", "conversation-2")], clicked


@pytest.mark.asyncio
async def test_textual_app_restores_saved_session_and_loads_conversation_history():
    client = FakeClient()
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: client)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.client is client
        assert str(app.query_one("#identity").render()) == "Signed in as user-1"
        assert app.conversations[0]["id"] == "conversation-1"
        await pilot.click("#sign-out")
        await pilot.pause()
        assert str(app.query_one("#identity").render()) == "Signed out"

    assert app.auth.logged_out
