"""Chat-first Textual client for the REST Agent API."""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
import threading
from typing import Any, Callable, Protocol

from rich.markdown import Markdown
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Button, Footer, Header, Input, Static

from .auth import DeviceLogin, TokenResponse
from .local_state import ConversationSelectionStore, JsonConversationSelectionStore


class ConversationClient(Protocol):
    def list_conversations(self) -> list[dict[str, Any]]: ...
    def create_conversation(self, title: str = "New conversation") -> dict[str, Any]: ...
    def rename_conversation(self, conversation_id: str, title: str) -> dict[str, Any]: ...
    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]: ...
    def cancel_run(self, run_id: str) -> dict[str, Any]: ...
    def ask(self, message: str, *, conversation_id: str | None = None, on_event=None) -> dict[str, Any]: ...


Command = Callable[[str], Any]


class ToolApprovalScreen(ModalScreen[bool]):
    CSS = "ToolApprovalScreen { align: center middle; } #approval { width: 70; height: auto; border: round $accent; padding: 1 2; background: $panel; } #approval-buttons { height: 3; align: center middle; }"

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self.payload = payload

    def compose(self) -> ComposeResult:
        command = " ".join(str(arg) for arg in self.payload.get("args", []))
        yield Static(f"Approve local {self.payload.get('tool', 'tool')} command?\n\n{command}", id="approval")
        yield Button("Approve", variant="success", id="approve")
        yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")


class TextualAgentApp(App[None]):
    TITLE = "DevOps Agent"
    SUB_TITLE = "Chat"
    CSS = """
    #status { height: 1; color: $text-muted; }
    #messages { height: 1fr; overflow-y: auto; padding: 1 2; }
    #message { dock: bottom; margin: 0 1 1 1; }
    .entry { height: auto; margin-bottom: 1; }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self, auth: DeviceLogin, client_factory,
                 selection_store: ConversationSelectionStore | None = None,
                 on_signed_in: Callable[[TokenResponse], None] | None = None) -> None:
        super().__init__()
        self.auth = auth
        self.client_factory = client_factory
        self.selection_store = selection_store
        self.on_signed_in = on_signed_in
        self._local_helper: subprocess.Popen | None = None
        self.client: ConversationClient | None = None
        self.conversations: list[dict[str, Any]] = []
        self.selected_conversation_id: str | None = None
        self.active_run_id: str | None = None
        self._assistant_bubble: Static | None = None
        self._assistant_content = ""
        self.commands: dict[str, tuple[str, Command]] = {
            "help": ("Show available commands", self._cmd_help),
            "new": ("Start a chat: /new [title]", self._cmd_new),
            "resume": ("List chats or resume one: /resume [number|id]", self._cmd_resume),
            "rename": ("Rename this chat: /rename <title>", self._cmd_rename),
            "cancel": ("Cancel the active run", self._cmd_cancel),
            "logout": ("Sign out and open browser sign-in", self._cmd_logout),
        }

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Starting…", id="status")
        yield Vertical(id="messages")
        yield Input(placeholder="Message your agent…  (/help for commands)", id="message")
        yield Footer()

    def on_mount(self) -> None:
        self.restore_session()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "message":
            self.send_message()

    @work(exclusive=True, group="auth")
    async def restore_session(self) -> None:
        try:
            tokens = await asyncio.to_thread(self.auth.restore)
            if tokens is None:
                self.query_one("#status", Static).update("Opening browser sign-in…")
                self.auth.verification_callback = self._show_verification
                tokens = await asyncio.to_thread(self.auth.sign_in)
            self._activate(tokens)
            await self._open_initial_chat()
        except Exception as error:
            self.query_one("#status", Static).update(f"Sign-in failed: {error}. Restart to try again.")

    def _activate(self, tokens: TokenResponse) -> None:
        self.client = self.client_factory(tokens)
        if self.on_signed_in is not None:
            helper = self.on_signed_in(tokens)
            if isinstance(helper, subprocess.Popen):
                self._local_helper = helper
                threading.Thread(target=self._watch_helper, daemon=True).start()

    def _watch_helper(self) -> None:
        process = self._local_helper
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "approval_request":
                self.call_from_thread(self._show_tool_approval, event)

    def _show_tool_approval(self, payload: dict[str, Any]) -> None:
        self.push_screen(
            ToolApprovalScreen(payload),
            lambda approved: self._reply_tool_approval(bool(approved)),
        )

    def _reply_tool_approval(self, approved: bool) -> None:
        process = self._local_helper
        if process is None or process.stdin is None or process.poll() is not None:
            return
        process.stdin.write(json.dumps({"approved": approved}) + "\n")
        process.stdin.flush()
        self.query_one("#status", Static).update(f"Signed in as {tokens.user_id}")

    async def _open_initial_chat(self) -> None:
        assert self.client is not None
        self.conversations = await asyncio.to_thread(self.client.list_conversations)
        saved = await asyncio.to_thread(self.selection_store.load) if self.selection_store else None
        selected = next((c for c in self.conversations if str(c.get("id")) == saved), None)
        if selected is None:
            selected = await asyncio.to_thread(self.client.create_conversation)
            self.conversations.insert(0, selected)
        self.selected_conversation_id = str(selected["id"])
        await self._save_selection()
        await self._load_messages()
        self.query_one("#message", Input).focus()
        self.query_one("#status", Static).update(f"{selected.get('title', 'Chat')} · signed in")

    async def _load_messages(self) -> None:
        if self.client is None or self.selected_conversation_id is None:
            return
        messages = await asyncio.to_thread(self.client.list_messages, self.selected_conversation_id)
        container = self.query_one("#messages", Vertical)
        await container.remove_children()
        for message in messages:
            role = str(message.get("role", "assistant")).capitalize()
            content = str(message.get("content", ""))
            await container.mount(self._make_message(role, content))

    def _make_message(self, role: str, content: str) -> Static:
        if role.lower() == "assistant":
            return Static(Markdown(content), classes="entry")
        return Static(Text(f"{role}: {content}"), classes="entry")

    @work(exclusive=True, group="messages")
    async def send_message(self) -> None:
        field = self.query_one("#message", Input)
        content = field.value.strip()
        if not content:
            return
        field.value = ""
        if content.startswith("/"):
            await self._dispatch_command(content)
            return
        if self.client is None or self.selected_conversation_id is None:
            self.query_one("#status", Static).update("Waiting for browser sign-in…")
            return
        container = self.query_one("#messages", Vertical)
        await container.mount(self._make_message("You", content))
        self._assistant_content = ""
        self._assistant_bubble = Static(Markdown(""), classes="entry")
        await container.mount(self._assistant_bubble)
        self.active_run_id = None
        self.query_one("#status", Static).update("Thinking…")
        try:
            result = await asyncio.to_thread(self.client.ask, content,
                conversation_id=self.selected_conversation_id, on_event=self._on_agent_event)
            final = str(result.get("message", ""))
            if final and not self._assistant_content:
                self._append_assistant(final)
            self.query_one("#status", Static).update("Ready")
        except Exception as error:
            self.query_one("#status", Static).update(f"Request failed: {error}")

    async def _dispatch_command(self, raw: str) -> None:
        try:
            words = shlex.split(raw[1:])
        except ValueError as error:
            self.query_one("#status", Static).update(f"Command syntax: {error}")
            return
        if not words:
            return
        command = self.commands.get(words[0].lower())
        if command is None:
            self.query_one("#status", Static).update(f"Unknown command /{words[0]}; use /help")
            return
        await command[1](" ".join(words[1:]))

    def register_command(self, name: str, description: str, handler: Command) -> None:
        """Register a future chat command without adding UI controls."""
        key = name.strip().lower().lstrip("/")
        if not key or not key.replace("-", "").isalnum():
            raise ValueError("command names must be alphanumeric or hyphenated")
        self.commands[key] = (description, handler)

    async def _cmd_help(self, _args: str) -> None:
        self._system_message("\n".join(f"/{name} — {description}" for name, (description, _) in self.commands.items()))

    async def _cmd_new(self, title: str) -> None:
        if self.client is None:
            return
        item = await asyncio.to_thread(self.client.create_conversation, title or "New conversation")
        self.conversations.insert(0, item)
        self.selected_conversation_id = str(item["id"])
        await self._save_selection()
        await self._load_messages()
        self.query_one("#status", Static).update(str(item.get("title", "New conversation")))

    async def _cmd_resume(self, target: str) -> None:
        if self.client is None:
            return
        self.conversations = await asyncio.to_thread(self.client.list_conversations)
        if not target:
            self._system_message("\n".join(f"{i}. {c.get('title', 'Untitled')} [{c.get('id')}]" for i, c in enumerate(self.conversations, 1)) or "No chats yet.")
            return
        match = None
        if target.isdigit() and 1 <= int(target) <= len(self.conversations):
            match = self.conversations[int(target) - 1]
        else:
            matches = [c for c in self.conversations if str(c.get("id", "")).startswith(target)]
            if len(matches) == 1:
                match = matches[0]
        if match is None:
            self.query_one("#status", Static).update("Chat not found (or id is ambiguous); use /resume")
            return
        self.selected_conversation_id = str(match["id"])
        await self._save_selection()
        await self._load_messages()
        self.query_one("#status", Static).update(str(match.get("title", "Chat")))

    async def _cmd_rename(self, title: str) -> None:
        if self.client is None or self.selected_conversation_id is None or not title.strip():
            self.query_one("#status", Static).update("Usage: /rename <title>")
            return
        await asyncio.to_thread(self.client.rename_conversation, self.selected_conversation_id, title.strip())
        self.query_one("#status", Static).update(f"Renamed chat to {title.strip()}")

    async def _cmd_cancel(self, _args: str) -> None:
        if self.client is not None and self.active_run_id:
            await asyncio.to_thread(self.client.cancel_run, self.active_run_id)
            self.query_one("#status", Static).update("Run cancelled")
        else:
            self.query_one("#status", Static).update("No active run")

    async def _cmd_logout(self, _args: str) -> None:
        if self.client is not None:
            await asyncio.to_thread(self.auth.logout)
        self.client = None
        self.selected_conversation_id = None
        if self.selection_store:
            await asyncio.to_thread(self.selection_store.clear)
        await self.query_one("#messages", Vertical).remove_children()
        self.query_one("#status", Static).update("Signed out · opening browser sign-in…")
        self.auth.verification_callback = self._show_verification
        try:
            tokens = await asyncio.to_thread(self.auth.sign_in)
            self._activate(tokens)
            await self._open_initial_chat()
        except Exception as error:
            self.query_one("#status", Static).update(f"Sign-in failed: {error}")

    def _system_message(self, message: str) -> None:
        self.call_from_thread(self._mount_system_message, message) if not self.is_running else self.run_worker(self._mount_system_message_async(message))

    async def _mount_system_message_async(self, message: str) -> None:
        await self.query_one("#messages", Vertical).mount(self._make_message("System", message))

    def _mount_system_message(self, message: str) -> None:
        self.run_worker(self._mount_system_message_async(message))

    async def _save_selection(self) -> None:
        if self.selection_store and self.selected_conversation_id:
            await asyncio.to_thread(self.selection_store.save, self.selected_conversation_id)

    def _show_verification(self, url: str, code: str) -> None:
        self.call_from_thread(self.query_one("#status", Static).update,
            f"Approve in browser: {url} · code {code}")

    def _on_agent_event(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else event
        if event.get("run_id"):
            self.call_from_thread(setattr, self, "active_run_id", str(event["run_id"]))
        if kind == "agent_delta":
            self.call_from_thread(self._append_assistant, str(data.get("text", event.get("text", ""))))
        elif kind in {"tool_call_started", "tool_call_completed"}:
            name = data.get("name", "tool")
            status = "running" if kind == "tool_call_started" else data.get("status", "completed")
            self.call_from_thread(self._mount_system_message, f"Tool call: {name} — {status}")
        elif kind == "agent_message":
            self.call_from_thread(self._set_assistant, str(event.get("message", "")))

    def _append_assistant(self, fragment: str) -> None:
        self._assistant_content += fragment
        if self._assistant_bubble is not None:
            self._assistant_bubble.update(Markdown(self._assistant_content))

    def _set_assistant(self, content: str) -> None:
        self._assistant_content = content
        if self._assistant_bubble is not None:
            self._assistant_bubble.update(Markdown(content))


def run_textual_app(auth: DeviceLogin, client_factory, on_signed_in=None) -> None:
    TextualAgentApp(auth, client_factory, JsonConversationSelectionStore(), on_signed_in).run()


__all__ = ["ConversationClient", "TextualAgentApp", "run_textual_app"]
