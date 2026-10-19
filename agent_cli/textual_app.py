"""Authenticated conversation UI built on Textual and the REST client seam."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, ListItem, ListView, RichLog, Static

from .auth import DeviceLogin, TokenResponse
from .local_state import ConversationSelectionStore, JsonConversationSelectionStore


class ConversationClient(Protocol):
    def list_conversations(self) -> list[dict[str, Any]]: ...
    def create_conversation(self, title: str = "New conversation") -> dict[str, Any]: ...
    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]: ...
    def cancel_run(self, run_id: str) -> dict[str, Any]: ...
    def ask(self, message: str, *, conversation_id: str | None = None, on_event=None) -> dict[str, Any]: ...


class TextualAgentApp(App[None]):
    TITLE = "DevOps Agent"
    SUB_TITLE = "Conversations"
    CSS = """
    #layout { height: 1fr; }
    #sidebar { width: 32; height: 1fr; border: round $accent; padding: 1; }
    #conversation-list { height: 1fr; }
    #chat { width: 1fr; height: 1fr; border: round $accent; padding: 1; }
    #messages { height: 1fr; border: round $surface; }
    #composer { height: auto; }
    #composer Input { width: 1fr; min-width: 8; }
    #composer Button { width: 12; min-width: 12; }
    #cancel-run { width: 12; min-width: 12; }
    #status { height: auto; min-height: 2; }
    #identity { height: auto; min-height: 2; color: $text-muted; }
    """

    def __init__(
        self,
        auth: DeviceLogin,
        client_factory,
        selection_store: ConversationSelectionStore | None = None,
    ) -> None:
        super().__init__()
        self.auth = auth
        self.client_factory = client_factory
        self.selection_store = selection_store
        self.client: ConversationClient | None = None
        self.conversations: list[dict[str, Any]] = []
        self.selected_conversation_id: str | None = None
        self.active_run_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Checking saved sign-in…", id="status")
        with Horizontal(id="layout"):
            with Vertical(id="sidebar"):
                yield Static("Signed out", id="identity")
                yield Button("Sign in", id="sign-in", variant="primary")
                yield Button("Create account", id="sign-up")
                yield Button("New conversation", id="new-conversation")
                yield Button("Sign out", id="sign-out", variant="warning")
                yield ListView(id="conversation-list")
            with Vertical(id="chat"):
                yield RichLog(id="messages", markup=False, wrap=True)
                with Horizontal(id="composer"):
                    yield Input(placeholder="Message your agent…", id="message")
                    yield Button("Send", id="send", variant="primary")
                    yield Button("Cancel", id="cancel-run", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self.restore_session()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sign-in":
            self.authenticate("signin")
        elif event.button.id == "sign-up":
            self.authenticate("signup")
        elif event.button.id == "new-conversation":
            self.create_conversation()
        elif event.button.id == "sign-out":
            self.sign_out()
        elif event.button.id == "send":
            self.send_message()
        elif event.button.id == "cancel-run":
            self.cancel_run()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "message":
            self.send_message()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.index is None or event.index >= len(self.conversations):
            return
        conversation = self.conversations[event.index]
        self.selected_conversation_id = str(conversation["id"])
        if self.selection_store:
            self.selection_store.save(self.selected_conversation_id)
        self.run_worker(
            self.load_messages(self.selected_conversation_id),
            exclusive=True,
            group="messages",
        )

    @work(exclusive=True, group="auth")
    async def restore_session(self) -> None:
        try:
            tokens = await asyncio.to_thread(self.auth.restore)
            if tokens is None:
                self.query_one("#status", Static).update("Sign in to load your conversations.")
                return
            self._activate(tokens)
            await self.refresh_conversations()
            saved = await asyncio.to_thread(self.selection_store.load) if self.selection_store else None
            if saved and any(item.get("id") == saved for item in self.conversations):
                self.selected_conversation_id = saved
                await self.load_messages(saved)
        except Exception as error:
            self.query_one("#status", Static).update(f"Could not restore sign-in: {error}")

    @work(exclusive=True, group="auth")
    async def authenticate(self, mode: str) -> None:
        self.auth.verification_callback = self._show_verification
        action = self.auth.sign_up if mode == "signup" else self.auth.sign_in
        description = "account creation" if mode == "signup" else "sign-in"
        self.query_one("#status", Static).update(f"Opening browser for {description}…")
        try:
            tokens = await asyncio.to_thread(action)
            self._activate(tokens)
            await self.refresh_conversations()
        except Exception as error:
            self.query_one("#status", Static).update(f"Authentication failed: {error}")

    @work(exclusive=True, group="auth")
    async def sign_out(self) -> None:
        try:
            await asyncio.to_thread(self.auth.logout)
        finally:
            self.client = None
            self.query_one("#identity", Static).update("Signed out")
            if self.selection_store:
                await asyncio.to_thread(self.selection_store.clear)
            self.conversations.clear()
            self.selected_conversation_id = None
            self.query_one(ListView).clear()
            self.query_one(RichLog).clear()
            self.query_one("#status", Static).update("Signed out.")

    async def refresh_conversations(self) -> None:
        if self.client is None:
            return
        try:
            self.conversations = await asyncio.to_thread(self.client.list_conversations)
            listing = self.query_one(ListView)
            listing.clear()
            for conversation in self.conversations:
                listing.append(ListItem(Static(str(conversation.get("title", "Untitled")))))
            if self.conversations:
                self.query_one("#status", Static).update("Choose a conversation or start a new one.")
            else:
                self.query_one("#status", Static).update("No conversations yet. Start a new one.")
        except Exception as error:
            self.query_one("#status", Static).update(f"Could not load conversations: {error}")

    @work(exclusive=True, group="new-conversation")
    async def create_conversation(self) -> None:
        if self.client is None:
            self.query_one("#status", Static).update("Sign in before starting a conversation.")
            return
        try:
            item = await asyncio.to_thread(self.client.create_conversation)
            await self.refresh_conversations()
            self.selected_conversation_id = str(item["id"])
            if self.selection_store:
                await asyncio.to_thread(self.selection_store.save, self.selected_conversation_id)
            self.query_one(RichLog).clear()
            self.query_one("#messages", RichLog).write(f"Started: {item.get('title', 'New conversation')}")
            self.query_one("#status", Static).update("Conversation ready.")
        except Exception as error:
            self.query_one("#status", Static).update(f"Could not create conversation: {error}")

    async def load_messages(self, conversation_id: str) -> None:
        if self.client is None:
            return
        try:
            messages = await asyncio.to_thread(self.client.list_messages, conversation_id)
            log = self.query_one(RichLog)
            log.clear()
            for message in messages:
                role = str(message.get("role", "message")).capitalize()
                log.write(f"{role}: {message.get('content', '')}")
            self.query_one("#status", Static).update("Conversation loaded.")
        except Exception as error:
            self.query_one("#status", Static).update(f"Could not load messages: {error}")

    @work(exclusive=True, group="messages")
    async def send_message(self) -> None:
        message_input = self.query_one("#message", Input)
        content = message_input.value.strip()
        if not content:
            return
        if self.client is None or self.selected_conversation_id is None:
            self.query_one("#status", Static).update("Sign in and select or create a conversation first.")
            return
        message_input.value = ""
        self.active_run_id = None
        self.query_one(RichLog).write(f"You: {content}")
        self.query_one("#status", Static).update("Agent is working…")
        try:
            result = await asyncio.to_thread(
                self.client.ask,
                content,
                conversation_id=self.selected_conversation_id,
                on_event=self._on_agent_event,
            )
            if result.get("message"):
                self.query_one(RichLog).write(f"Agent: {result['message']}")
            self.query_one("#status", Static).update("Ready.")
            await self.refresh_conversations()
        except Exception as error:
            self.query_one("#status", Static).update(f"Request failed: {error}")

    @work(group="cancel")
    async def cancel_run(self) -> None:
        if self.client is None or self.active_run_id is None:
            self.query_one("#status", Static).update("No active run to cancel.")
            return
        try:
            result = await asyncio.to_thread(self.client.cancel_run, self.active_run_id)
            self.query_one("#status", Static).update(f"Run {result.get('status', 'cancelled')}.")
        except Exception as error:
            self.query_one("#status", Static).update(f"Could not cancel run: {error}")

    def _activate(self, tokens: TokenResponse) -> None:
        self.client = self.client_factory(tokens)
        self.query_one("#identity", Static).update(f"Signed in as {tokens.user_id}")
        self.query_one("#status", Static).update(f"Signed in as {tokens.user_id}.")

    def _show_verification(self, url: str, code: str) -> None:
        self.call_from_thread(
            self._set_status,
            f"Approve in browser at {url}; enter code {code}.",
        )

    def _on_agent_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "agent_message":
            self.call_from_thread(self._write_message, f"Agent: {event.get('message', '')}")
        elif event.get("type") == "run_event":
            self.call_from_thread(self._set_active_run, str(event.get("run_id", "")))
            self.call_from_thread(
                self._set_status,
                f"Agent run: {event.get('type', 'in progress')}.",
            )

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _write_message(self, message: str) -> None:
        self.query_one(RichLog).write(message)

    def _set_active_run(self, run_id: str) -> None:
        self.active_run_id = run_id or None


def run_textual_app(auth: DeviceLogin, client_factory) -> None:
    TextualAgentApp(auth, client_factory, JsonConversationSelectionStore()).run()


__all__ = ["ConversationClient", "TextualAgentApp", "run_textual_app"]
