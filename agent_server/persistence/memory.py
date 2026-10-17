"""Process-local conversation adapter for development and isolated tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from agent_core.conversations import Conversation, ConversationMessage


class InMemoryConversationRepository:
    """A concurrency-safe adapter; production deployments must inject durable storage."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[ConversationMessage]] = {}

    async def create(self, user_id: str, title: str) -> Conversation:
        now = datetime.now(timezone.utc)
        item = Conversation(uuid4().hex, user_id, title, now, now)
        async with self._lock:
            self._conversations[item.id] = item
            self._messages[item.id] = []
        return item

    async def list_for_user(self, user_id: str) -> tuple[Conversation, ...]:
        async with self._lock:
            values = (item for item in self._conversations.values() if item.user_id == user_id)
            return tuple(sorted(values, key=lambda item: item.updated_at, reverse=True))

    async def get(self, user_id: str, conversation_id: str) -> Conversation | None:
        async with self._lock:
            item = self._conversations.get(conversation_id)
            return item if item and item.user_id == user_id else None

    async def add_message(
        self, user_id: str, conversation_id: str, role: str, content: str
    ) -> ConversationMessage:
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError("unsupported message role")
        now = datetime.now(timezone.utc)
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None or conversation.user_id != user_id:
                raise LookupError("conversation not found")
            message = ConversationMessage(uuid4().hex, conversation_id, role, content, now)
            self._messages[conversation_id].append(message)
            self._conversations[conversation_id] = replace(conversation, updated_at=now)
            return message

    async def list_messages(
        self, user_id: str, conversation_id: str
    ) -> tuple[ConversationMessage, ...]:
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None or conversation.user_id != user_id:
                return ()
            return tuple(self._messages[conversation_id])


__all__ = ["InMemoryConversationRepository"]
