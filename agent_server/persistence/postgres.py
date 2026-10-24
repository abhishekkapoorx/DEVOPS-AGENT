"""PostgreSQL conversation adapter using SQLAlchemy's async engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    text,
    UniqueConstraint,
    and_,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agent_core.conversations import Conversation, ConversationMessage
from agent_core.runs import AgentRun, IdempotencyConflict, RunEvent, RunLeaseLost


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


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "conversation_id", "idempotency_key", name="uq_agent_run_idempotency"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversation_messages.id", ondelete="CASCADE")
    )
    input_message: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), index=True)
    attempt: Mapped[int] = mapped_column(BigInteger, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), default="")
    traceparent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RunEventRow(Base):
    __tablename__ = "run_events"

    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
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

    async def health_check(self) -> bool:
        try:
            async with self._sessions() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

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

    async def rename(self, user_id: str, conversation_id: str, title: str) -> Conversation | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.user_id == user_id,
                )
            )
            if row is None:
                return None
            row.title = title
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return _conversation(row)

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

    async def create_or_get_run(
        self,
        user_id: str,
        conversation_id: str,
        idempotency_key: str,
        request_hash: str,
        content: str,
        *,
        correlation_id: str = "",
        traceparent: str | None = None,
    ) -> tuple[AgentRun, bool]:
        now = datetime.now(timezone.utc)
        run_id = uuid4().hex
        message_id = uuid4().hex
        try:
            async with self._sessions() as session:
                conversation = await session.scalar(
                    select(ConversationRow).where(
                        ConversationRow.id == conversation_id,
                        ConversationRow.user_id == user_id,
                    )
                )
                if conversation is None:
                    raise LookupError("conversation not found")
                existing = await session.scalar(
                    select(AgentRunRow).where(
                        AgentRunRow.user_id == user_id,
                        AgentRunRow.conversation_id == conversation_id,
                        AgentRunRow.idempotency_key == idempotency_key,
                    )
                )
                if existing is not None:
                    if existing.request_hash != request_hash:
                        raise IdempotencyConflict(
                            "Idempotency-Key was already used for another message"
                        )
                    return _run(existing), False

                message = MessageRow(
                    id=message_id,
                    conversation_id=conversation_id,
                    role="user",
                    content=content,
                    created_at=now,
                )
                run = AgentRunRow(
                    id=run_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    message_id=message_id,
                    input_message=content,
                    state="pending",
                    correlation_id=correlation_id,
                    traceparent=traceparent,
                    attempt=0,
                    lease_owner=None,
                    lease_expires_at=None,
                    message="",
                    tool_calls=[],
                    created_at=now,
                    updated_at=now,
                )
                conversation.updated_at = now
                # The run's message_id is an immediate PostgreSQL FK. Flush the
                # parent row first instead of relying on unit-of-work ordering
                # between independent mappers (there is no ORM relationship).
                session.add(message)
                await session.flush()
                session.add(run)
                await session.flush()
                session.add(
                    RunEventRow(
                        run_id=run_id,
                        event_type="created",
                        data={"state": "pending"},
                        created_at=now,
                    )
                )
                await session.commit()
                return _run(run), True
        except IntegrityError:
            async with self._sessions() as session:
                existing = await session.scalar(
                    select(AgentRunRow).where(
                        AgentRunRow.user_id == user_id,
                        AgentRunRow.conversation_id == conversation_id,
                        AgentRunRow.idempotency_key == idempotency_key,
                    )
                )
            if existing is None:
                raise
            if existing.request_hash != request_hash:
                raise IdempotencyConflict("Idempotency-Key was already used for another message")
            return _run(existing), False

    async def claim_next_run(self, worker_id: str, lease_seconds: int) -> AgentRun | None:
        now = datetime.now(timezone.utc)
        async with self._sessions() as session:
            async with session.begin():
                row = await session.scalar(
                    select(AgentRunRow)
                    .where(
                        or_(
                            AgentRunRow.state == "pending",
                            and_(
                                AgentRunRow.state == "running",
                                AgentRunRow.lease_expires_at <= now,
                            ),
                        )
                    )
                    .order_by(AgentRunRow.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if row is None:
                    return None
                prior_attempt = row.attempt
                row.state = "running"
                row.attempt += 1
                row.lease_owner = worker_id
                row.lease_expires_at = now + timedelta(seconds=lease_seconds)
                row.updated_at = now
                session.add(
                    RunEventRow(
                        run_id=row.id,
                        event_type="running" if prior_attempt == 0 else "resumed",
                        data={"state": "running", "attempt": row.attempt},
                        created_at=now,
                    )
                )
                return _run(row)

    async def renew_run_lease(self, worker_id: str, run_id: str, lease_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        async with self._sessions() as session:
            result = await session.execute(
                update(AgentRunRow)
                .where(
                    AgentRunRow.id == run_id,
                    AgentRunRow.state == "running",
                    AgentRunRow.lease_owner == worker_id,
                )
                .values(
                    lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now
                )
            )
            await session.commit()
            return result.rowcount == 1

    async def append_run_event(self, user_id, run_id, worker_id, event_type, data):
        now = datetime.now(timezone.utc)
        async with self._sessions() as session:
            row = await session.scalar(
                select(AgentRunRow).where(
                    AgentRunRow.id == run_id,
                    AgentRunRow.user_id == user_id,
                    AgentRunRow.state == "running",
                    AgentRunRow.lease_owner == worker_id,
                )
            )
            if row is None:
                raise RunLeaseLost("run lease is no longer owned by this worker")
            event = RunEventRow(
                run_id=run_id, event_type=event_type, data=dict(data), created_at=now
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return RunEvent(event.sequence, event.run_id, event.event_type, event.data, event.created_at)

    async def complete_run(
        self, user_id: str, run_id: str, worker_id: str, message: str, tool_calls
    ) -> AgentRun:
        async with self._sessions() as session:
            row = await _owned_run(session, user_id, run_id)
            if row.lease_owner != worker_id:
                raise RunLeaseLost("run lease is no longer owned by this worker")
            if row.state != "completed":
                now = datetime.now(timezone.utc)
                calls = [dict(call) for call in tool_calls]
                row.state = "completed"
                row.message = message
                row.tool_calls = calls
                row.lease_owner = None
                row.lease_expires_at = None
                row.updated_at = now
                if message:
                    session.add(
                        MessageRow(
                            id=uuid4().hex,
                            conversation_id=row.conversation_id,
                            role="assistant",
                            content=message,
                            created_at=now,
                        )
                    )
                session.add(
                    RunEventRow(
                        run_id=run_id,
                        event_type="completed",
                        data={"state": "completed", "message": message, "tool_calls": calls},
                        created_at=now,
                    )
                )
                await session.commit()
            return _run(row)

    async def fail_run(
        self, user_id: str, run_id: str, worker_id: str, error: str
    ) -> AgentRun:
        async with self._sessions() as session:
            row = await _owned_run(session, user_id, run_id)
            if row.lease_owner != worker_id:
                raise RunLeaseLost("run lease is no longer owned by this worker")
            if row.state not in {"completed", "failed"}:
                now = datetime.now(timezone.utc)
                row.state = "failed"
                row.error = error
                row.lease_owner = None
                row.lease_expires_at = None
                row.updated_at = now
                session.add(
                    RunEventRow(
                        run_id=run_id,
                        event_type="failed",
                        data={"state": "failed", "error": error},
                        created_at=now,
                    )
                )
                await session.commit()
            return _run(row)

    async def cancel_run(self, user_id: str, run_id: str) -> AgentRun | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(AgentRunRow).where(
                    AgentRunRow.id == run_id, AgentRunRow.user_id == user_id
                ).with_for_update()
            )
            if row is None:
                return None
            if row.state not in {"completed", "failed", "cancelled", "expired"}:
                now = datetime.now(timezone.utc)
                row.state = "cancelled"
                row.lease_owner = None
                row.lease_expires_at = None
                row.updated_at = now
                session.add(
                    RunEventRow(
                        run_id=run_id,
                        event_type="cancelled",
                        data={"state": "cancelled"},
                        created_at=now,
                    )
                )
                await session.commit()
            return _run(row)

    async def get_run(self, user_id: str, run_id: str) -> AgentRun | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(AgentRunRow).where(
                    AgentRunRow.id == run_id, AgentRunRow.user_id == user_id
                )
            )
        return _run(row) if row else None

    async def list_run_events(self, user_id: str, run_id: str, after: int = 0):
        async with self._sessions() as session:
            owner = await session.scalar(
                select(AgentRunRow.id).where(
                    AgentRunRow.id == run_id, AgentRunRow.user_id == user_id
                )
            )
            if owner is None:
                return ()
            rows = (
                await session.scalars(
                    select(RunEventRow)
                    .where(RunEventRow.run_id == run_id, RunEventRow.sequence > after)
                    .order_by(RunEventRow.sequence)
                )
            ).all()
        return tuple(
            RunEvent(row.sequence, row.run_id, row.event_type, row.data, row.created_at)
            for row in rows
        )

async def _owned_run(session: AsyncSession, user_id: str, run_id: str) -> AgentRunRow:
    row = await session.scalar(
        select(AgentRunRow).where(AgentRunRow.id == run_id, AgentRunRow.user_id == user_id)
    )
    if row is None:
        raise LookupError("run not found")
    return row


def _conversation(row: ConversationRow) -> Conversation:
    return Conversation(row.id, row.user_id, row.title, row.created_at, row.updated_at)


def _message(row: MessageRow) -> ConversationMessage:
    return ConversationMessage(row.id, row.conversation_id, row.role, row.content, row.created_at)


def _run(row: AgentRunRow) -> AgentRun:
    return AgentRun(
        id=row.id,
        user_id=row.user_id,
        conversation_id=row.conversation_id,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        message_id=row.message_id,
        input_message=row.input_message,
        state=row.state,
        attempt=row.attempt,
        lease_owner=row.lease_owner,
        lease_expires_at=row.lease_expires_at,
        message=row.message,
        tool_calls=tuple(row.tool_calls or ()),
        error=row.error,
        correlation_id=row.correlation_id or "",
        traceparent=row.traceparent,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


__all__ = ["Base", "PostgresConversationRepository", "create_session_factory"]
