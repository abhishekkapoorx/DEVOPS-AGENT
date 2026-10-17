"""PostgreSQL conversation adapter using SQLAlchemy's async engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agent_core.conversations import Conversation, ConversationMessage


class Base(DeclarativeBase):
    pass


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MessageRow(Base):
    __tablename__ = "conversation_messages"

    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(32), unique=True, default=lambda: uuid4().hex)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def create_session_factory(database_url: str) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    """Create an async engine and session factory from a PostgreSQL URL."""

    url = database_url
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("DATABASE_URL must use PostgreSQL")
    engine = create_async_engine(url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


class PostgresConversationRepository:
    """Durable ConversationRepository adapter with ownership-scoped queries."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, user_id: str, title: str) -> Conversation:
        now = datetime.now(timezone.utc)
        row = ConversationRow(
            id=uuid4().hex, user_id=user_id, title=title, created_at=now, updated_at=now
        )
        async with self._sessions() as session:
            session.add(row)
            await session.commit()
        return _conversation(row)

    async def list_for_user(self, user_id: str) -> tuple[Conversation, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ConversationRow)
                    .where(ConversationRow.user_id == user_id)
                    .order_by(ConversationRow.updated_at.desc())
                )
            ).all()
        return tuple(_conversation(row) for row in rows)

    async def get(self, user_id: str, conversation_id: str) -> Conversation | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.user_id == user_id,
                )
            )
        return _conversation(row) if row else None

    async def add_message(
        self, user_id: str, conversation_id: str, role: str, content: str
    ) -> ConversationMessage:
        now = datetime.now(timezone.utc)
        async with self._sessions() as session:
            conversation = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.user_id == user_id,
                )
            )
            if conversation is None:
                raise LookupError("conversation not found")
            row = MessageRow(
                id=uuid4().hex,
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_at=now,
            )
            conversation.updated_at = now
            session.add(row)
            await session.commit()
        return _message(row)

    async def list_messages(
        self, user_id: str, conversation_id: str
    ) -> tuple[ConversationMessage, ...]:
        async with self._sessions() as session:
            owner = await session.scalar(
                select(ConversationRow.id).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.user_id == user_id,
                )
            )
            if owner is None:
                return ()
            rows = (
                await session.scalars(
                    select(MessageRow)
                    .where(MessageRow.conversation_id == conversation_id)
                    .order_by(MessageRow.sequence)
                )
            ).all()
        return tuple(_message(row) for row in rows)


def _conversation(row: ConversationRow) -> Conversation:
    return Conversation(row.id, row.user_id, row.title, row.created_at, row.updated_at)


def _message(row: MessageRow) -> ConversationMessage:
    return ConversationMessage(row.id, row.conversation_id, row.role, row.content, row.created_at)


__all__ = ["Base", "PostgresConversationRepository", "create_session_factory"]
