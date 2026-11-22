from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console
from rich.markdown import Markdown
from textual.binding import Binding
from textual.widgets import Button, Input, OptionList, Static

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

    def list_conversation_events(self, conversation_id):
        return [
            {
                "sequence": 1,
                "run_id": "run-older",
                "type": "user_message",
                "data": {"role": "user", "content": f"history for {conversation_id}"},
            },
            {
                "sequence": 2,
                "run_id": "run-older",
                "type": "tool_call_started",
                "data": {"call_id": "old-call", "name": "git.status"},
            },
            {
                "sequence": 3,
                "run_id": "run-older",
                "type": "tool_call_completed",
                "data": {
                    "call_id": "old-call",
                    "name": "git.status",
                    "status": "succeeded",
                    "result": {"output": {"branch": "main"}},
                },
            },
            {
                "sequence": 4,
                "run_id": "run-older",
                "type": "subagent_started",
                "data": {
                    "namespace": ["security_agent:task-9"],
                    "name": "security_agent",
                },
            },
            {
                "sequence": 5,
                "run_id": "run-older",
                "type": "subagent_update",
                "data": {
                    "namespace": ["security_agent:task-9"],
                    "node": "inspect_rules",
                    "updated_keys": ["finding_count"],
                },
            },
            {
                "sequence": 6,
                "run_id": "run-older",
                "type": "agent_delta",
                "data": {
                    "namespace": ["security_agent:task-9"],
                    "text": "Found two findings",
                },
            },
            {
                "sequence": 7,
                "run_id": "run-older",
                "type": "subagent_completed",
                "data": {
                    "namespace": ["security_agent:task-9"],
                    "name": "security_agent",
                    "status": "completed",
                },
            },
            {
                "sequence": 8,
                "run_id": "run-older",
                "type": "graph_step",
                "data": {"node": "inspect", "result": {"findings": 2}},
            },
            {
                "sequence": 9,
                "run_id": "run-older",
                "type": "assistant_message",
                "data": {"role": "assistant", "content": "**Previously done**"},
            },
        ]

    def ask(self, message, *, conversation_id=None, on_event=None):
        self.sent.append((message, conversation_id))
        for conversation in self.conversations:
            if conversation["id"] == conversation_id and conversation["title"] == "New conversation":
                conversation["title"] = "Generated from first prompt"
        if on_event:
            on_event({"type": "agent_delta", "text": "Hello, "})
            on_event({"type": "tool_call_started", "data": {"name": "git.status", "call_id": "c1"}})
            on_event({
                "type": "tool_call_completed",
                "data": {
                    "call_id": "c1",
                    "name": "git.status",
                    "status": "succeeded",
                    "result": {
                        "status": "succeeded",
                    "output": {
                        "branch": "main",
                        "clean": True,
                        "details": "x" * 1500,
                    },
                    },
                },
            })
            on_event({"type": "agent_delta", "text": "world!"})
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
        assert "git.status" not in run_status
        assert "Hello," in transcript
        assert "world!" in transcript
        assert "**Hello" not in transcript
        assert isinstance(app._assistant_bubble._Static__content, Markdown)


@pytest.mark.asyncio
async def test_tool_activity_expands_and_collapses_inline_without_opening_a_modal():
    client = FakeClient()
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: client, FakeSelectionStore())

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.2)
        composer = app.query_one("#message", Input)
        composer.value = "check git status"
        await pilot.press("enter")
        await pilot.pause(0.2)

        card = app.query_one("#tool-c1")
        timeline_children = list(app.query_one("#messages").children)
        card_index = timeline_children.index(card)
        assert any(
            child.has_class("entry") for child in timeline_children[:card_index]
        )
        assert any(
            child.has_class("entry") for child in timeline_children[card_index + 1:]
        )
        tool_name = app.query_one("#tool-c1 .tool-name", Static)
        tool_status = app.query_one("#tool-c1 .tool-status", Static)
        assert "git.status" in render_widget(tool_name)
        assert "succeeded" in render_widget(tool_status)
        assert tool_name.styles.color.hex == app.theme_variables["primary"]
        assert tool_status.styles.color.hex != tool_name.styles.color.hex
        preview_panel = app.query_one("#tool-c1 .tool-activity-preview-panel")
        assert not preview_panel.display

        await pilot.click(card)
        assert preview_panel.display
        preview = app.query_one("#tool-c1 .tool-activity-preview", Static)
        assert "branch" in render_widget(preview)
        assert "x" * 1500 in preview.content.plain

        await pilot.click(card)
        await pilot.pause(0.1)
        assert not preview_panel.display
        assert "git.status" in render_widget(tool_name)
        assert not app.screen.query("#full-tool-output")

        await pilot.click(card)
        assert preview_panel.display
        assert "branch" in render_widget(preview)


@pytest.mark.asyncio
async def test_chat_text_can_be_selected_with_mouse_and_copied_with_ctrl_c():
    app = TextualAgentApp(
        FakeAuth(tokens=token()),
        lambda _tokens: FakeClient(),
        FakeSelectionStore(selected="conversation-1"),
    )

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.2)
        message = app.query_one("#messages .entry", Static)

        await pilot.mouse_down(message, offset=(6, 0))
        await pilot.mouse_up(message, offset=(18, 0))
        await pilot.press("ctrl+c")

        assert "history for" in app.clipboard


@pytest.mark.asyncio
async def test_resumed_chat_restores_persisted_tool_call_and_output_inline():
    app = TextualAgentApp(
        FakeAuth(tokens=token()),
        lambda _tokens: FakeClient(),
        FakeSelectionStore(selected="conversation-1"),
    )

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.2)
        card = app.query_one("#tool-old-call")
        assert "git.status" in render_widget(app.query_one("#tool-old-call .tool-name", Static))
        assert "succeeded" in render_widget(app.query_one("#tool-old-call .tool-status", Static))
        card.action_activate()
        output = app.query_one("#tool-old-call .tool-activity-preview", Static)
        assert '"branch": "main"' in output.content.plain
        subagent = app.query_one("#tool-subagent-security_agent_task-9")
        assert "security_agent" in render_widget(
            app.query_one("#tool-subagent-security_agent_task-9 .tool-name", Static)
        )
        assert "completed" in render_widget(
            app.query_one("#tool-subagent-security_agent_task-9 .tool-status", Static)
        )
        subagent_preview = app.query_one(
            "#tool-subagent-security_agent_task-9 .tool-activity-preview", Static
        )
        assert "Found two findings" in subagent_preview.content.plain
        graph_step = app.query_one("#tool-graph-step-run-older-inspect")
        graph_step.action_activate()
        graph_preview = app.query_one(
            "#tool-graph-step-run-older-inspect .tool-activity-preview", Static
        )
        assert '"findings": 2' in graph_preview.content.plain


def test_copy_and_export_shortcuts_are_hidden_from_footer():
    bindings = [
        binding if isinstance(binding, Binding) else Binding(*binding)
        for binding in TextualAgentApp.BINDINGS
    ]

    hidden_actions = {binding.description for binding in bindings if not binding.show}
    assert {"Copy chat", "Export chat"} <= hidden_actions


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


@pytest.mark.asyncio
async def test_slash_suggestions_filter_and_insert_command_at_cursor_context():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        composer = app.query_one("#message", Input)
        composer.value = "Review incident /he follow-up"
        composer.cursor_position = len("Review incident /he")
        await pilot.pause(0.1)

        suggestions = app.query_one("#command-suggestions", OptionList)
        assert suggestions.display
        assert suggestions.option_count == 1
        suggestion = str(suggestions.get_option_at_index(0).prompt)
        assert "/help" in suggestion
        assert "Show available commands" in suggestion

        await pilot.press("enter")

        assert composer.value == "Review incident /help follow-up"


@pytest.mark.asyncio
async def test_slash_suggestions_support_arrow_selection_and_escape_preserves_draft():
    app = TextualAgentApp(FakeAuth(tokens=token()), lambda _tokens: FakeClient())

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        composer = app.query_one("#message", Input)
        composer.value = "/"
        await pilot.pause(0.1)
        await pilot.press("down", "enter")

        assert composer.value == "/new"

        composer.value = "please /ne"
        composer.cursor_position = len(composer.value)
        await pilot.pause(0.1)
        assert app.query_one("#command-suggestions", OptionList).display

        await pilot.press("escape")

        assert composer.value == "please /ne"
        assert not app.query_one("#command-suggestions", OptionList).display


def token():
    return TokenResponse(
        access_token="access", refresh_token="refresh", expires_in=60, user_id="user-1"
    )
