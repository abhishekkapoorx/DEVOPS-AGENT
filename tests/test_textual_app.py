from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console
from rich.markdown import Markdown
from textual.widgets import Button, Input, Static

from agent_cli.auth import TokenResponse
from agent_cli.textual_app import (
    ConversationPickerScreen,
    ExportConversationScreen,
    TextualAgentApp,
    ToolApprovalScreen,
)


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
        self.created_titles = []
        self.renamed = []
        self.sent = []
        self.cancelled = []

    def list_conversations(self):
        return list(self.conversations)

    def create_conversation(self, title="New conversation"):
        self.created_titles.append(title)
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
        for conversation in self.conversations:
            if conversation["id"] == conversation_id and conversation["title"] == "New conversation":
                conversation["title"] = "Generated from first prompt"
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
        assert app.selected_conversation_id is None
        assert client.created == []
        assert not app.query("#sign-in").nodes
        assert not app.query("#sign-up").nodes
        assert not app.query("#conversation-list").nodes
        assert app.query_one("#message", Input).has_focus


@pytest.mark.asyncio
async def test_empty_input_does_not_create_a_chat_and_first_prompt_refreshes_its_title():
    client = FakeClient()
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: client, FakeSelectionStore())

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.2)
        composer = app.query_one("#message", Input)

        composer.value = "   "
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert client.created == []

        composer.value = "Summarize deployment failures"
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert client.created_titles[-1] == "New conversation"
        assert client.sent[-1] == ("Summarize deployment failures", client.created[-1]["id"])
        assert "Generated from first prompt" in render_widget(app.query_one("#status", Static))


@pytest.mark.asyncio
async def test_chat_picker_uses_arrow_keys_and_enter_to_select_a_chat():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())
    selected = []
    conversations = [
        {"id": "chat-1", "title": "First chat"},
        {"id": "chat-2", "title": "Second chat"},
        {"id": "chat-3", "title": "Third chat"},
    ]

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        app.push_screen(ConversationPickerScreen(conversations), selected.append)
        await pilot.pause(0.1)

        await pilot.press("down", "down", "up", "enter")

        assert selected == ["chat-2"]


@pytest.mark.asyncio
async def test_escape_closes_the_chat_picker_without_selecting_a_chat():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())
    selected = []

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        app.push_screen(
            ConversationPickerScreen([{"id": "chat-1", "title": "First chat"}]),
            selected.append,
        )
        await pilot.pause(0.1)

        await pilot.press("escape")

        assert selected == [None]
        assert not isinstance(app.screen, ConversationPickerScreen)


@pytest.mark.asyncio
async def test_escape_cancels_export_modal():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())
    result = []

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        app.push_screen(ExportConversationScreen(), result.append)
        await pilot.pause(0.1)

        await pilot.press("escape")

        assert result == [None]
        assert not isinstance(app.screen, ExportConversationScreen)


@pytest.mark.asyncio
async def test_export_modal_accepts_a_path_from_the_keyboard():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())
    result = []

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        app.push_screen(ExportConversationScreen(), result.append)
        await pilot.pause(0.1)
        path_field = app.screen.query_one("#export-path", Input)
        path_field.value = "conversation.txt"

        await pilot.press("enter")

        assert result == ["conversation.txt"]


@pytest.mark.asyncio
async def test_escape_denies_tool_approval_modal():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())
    result = []

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        app.push_screen(ToolApprovalScreen({"name": "shell.run", "arguments": {}}), result.append)
        await pilot.pause(0.1)

        await pilot.press("escape")

        assert result == [False]
        assert not isinstance(app.screen, ToolApprovalScreen)


@pytest.mark.asyncio
async def test_tool_approval_modal_can_be_approved_with_enter():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())
    result = []

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        app.push_screen(ToolApprovalScreen({"name": "shell.run", "arguments": {}}), result.append)
        await pilot.pause(0.1)
        app.screen.query_one("#approve", Button).focus()

        await pilot.press("enter")

        assert result == [True]


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
        run_status = render_widget(app.query_one("#run-status", Static))
        assert "Tool call: git.status" not in transcript
        assert "Run completed" in run_status
        assert "git.status: succeeded" in run_status
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
        assert client.created == []
        assert app.selected_conversation_id is None

        composer.value = "Review the production incident"
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
