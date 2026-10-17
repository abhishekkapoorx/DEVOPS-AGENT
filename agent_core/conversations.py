"""Conversation contracts shared by API services and persistence adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Conversation:
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ConversationMessage:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


class ConversationRepository(Protocol):
    async def create(self, user_id: str, title: str) -> Conversation: ...
    async def list_for_user(self, user_id: str) -> Sequence[Conversation]: ...
    async def get(self, user_id: str, conversation_id: str) -> Conversation | None: ...
    async def add_message(
        self, user_id: str, conversation_id: str, role: str, content: str
    ) -> ConversationMessage: ...
    async def list_messages(
        self, user_id: str, conversation_id: str
    ) -> Sequence[ConversationMessage]: ...
