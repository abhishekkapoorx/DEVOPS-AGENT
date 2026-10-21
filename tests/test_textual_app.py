from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console
from rich.markdown import Markdown
from textual.widgets import Input, Static

from agent_cli.auth import TokenResponse
from agent_cli.textual_app import TextualAgentApp


class FakeAuth:
    def __init__(self, tokens=None):
        self.tokens = tokens
        self.verification_callback = lambda *_: None
        self.logged_out = False
        self.sign_in_calls = 0

    def restore(self):
        return self.tokens

    def sign_in(self):
        self.sign_in_calls += 1
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
        self.conversations = [{"id": "conversation-1", "title": "Existing"}]
        self.created = []
        self.renamed = []
        self.sent = []
        self.cancelled = []

    def list_conversations(self):
        return list(self.conversations)

    def create_conversation(self, title="New conversation"):
        conversation = {"id": f"conversation-{len(self.conversations) + 1}", "title": title}
        self.created.append(conversation)
        self.conversations.insert(0, conversation)
        return conversation

    def rename_conversation(self, conversation_id, title):
        self.renamed.append((conversation_id, title))
        for conversation in self.conversations:
            if conversation["id"] == conversation_id:
                conversation["title"] = title
                return conversation
        raise LookupError("missing conversation")

    def list_messages(self, conversation_id):
        return [
            {"role": "user", "content": f"history for {conversation_id}"},
            {"role": "assistant", "content": "**Previously done**"},
        ]

    def ask(self, message, *, conversation_id=None, on_event=None):
        self.sent.append((message, conversation_id))
        if on_event:
            on_event({"type": "agent_delta", "text": "**Hello, "})
            on_event({"type": "tool_call_started", "data": {"name": "git.status", "call_id": "c1"}})
            on_event({"type": "tool_call_completed", "data": {"name": "git.status", "status": "succeeded"}})
            on_event({"type": "agent_delta", "text": "world!**"})
        return {"message": "**Hello, world!**"}

    def cancel_run(self, run_id):
        self.cancelled.append(run_id)
        return {"status": "cancelled"}


class FakeSelectionStore:
    def __init__(self, selected=None):
        self.selected = selected

    def load(self):
        return self.selected

    def save(self, selected):
        self.selected = selected

    def clear(self):
        self.selected = None


def render_widget(widget: Static) -> str:
    output = StringIO()
    content = widget._Static__content  # Rich renderable used by Static (Markdown or Text).
    Console(file=output, force_terminal=False, width=100).print(content)
    return output.getvalue()


@pytest.mark.asyncio
async def test_signed_out_user_is_sent_to_browser_and_waits_in_chat_only_tui():
    auth = FakeAuth()
    client = FakeClient()
    app = TextualAgentApp(auth, lambda _tokens: client, FakeSelectionStore())

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.2)

        assert auth.sign_in_calls == 1
        assert app.client is client
        assert app.selected_conversation_id == "conversation-2"
        assert not app.query("#sign-in").nodes
        assert not app.query("#sign-up").nodes
        assert not app.query("#conversation-list").nodes
        assert app.query_one("#message", Input).has_focus


@pytest.mark.asyncio
async def test_chat_streams_markdown_and_registered_tool_activity():
    client = FakeClient()
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: client, FakeSelectionStore())

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.2)
        composer = app.query_one("#message", Input)
        composer.value = "check git status"
        await pilot.press("enter")
        await pilot.pause(0.2)

        rendered = [render_widget(widget) for widget in app.query("#messages Static")]
        transcript = "\n".join(rendered)
        assert "Tool call: git.status" in transcript
        assert "succeeded" in transcript
        assert "Hello, world!" in transcript
        assert "**Hello" not in transcript
        assert isinstance(app._assistant_bubble._Static__content, Markdown)


@pytest.mark.asyncio
async def test_slash_commands_create_rename_list_and_resume_conversations():
    client = FakeClient()
    store = FakeSelectionStore()
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: client, store)

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.2)
        composer = app.query_one("#message", Input)

        composer.value = "/new Incident review"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert client.created[-1]["title"] == "Incident review"
        new_id = client.created[-1]["id"]
        assert app.selected_conversation_id == new_id

        composer.value = "/rename Production incident"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert client.renamed[-1] == (new_id, "Production incident")

        composer.value = "/resume"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert "1. Production incident" in "\n".join(
            render_widget(widget) for widget in app.query("#messages Static")
        )

        composer.value = "/resume 2"
        await pilot.press("enter")
        await pilot.pause(0.1)
        expected_id = client.conversations[1]["id"]
        assert app.selected_conversation_id == expected_id
        assert store.selected == expected_id


def token():
    return TokenResponse(
        access_token="access", refresh_token="refresh", expires_in=60, user_id="user-1"
    )
