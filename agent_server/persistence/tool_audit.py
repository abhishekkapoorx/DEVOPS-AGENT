"""PostgreSQL persistence for registered Tool Call audit and idempotency."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from agent_core.runs import IdempotencyConflict
from agent_core.tools import ToolExecutionContext, ToolResult
from agent_protocol import redact_secrets

from .postgres import Base


class ToolExecutionRow(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_tool_execution_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    call_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(128))
    tool_version: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostgresToolExecutionRepository:
    """Persist idempotency claims before side effects and bounded results after."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def begin_tool_call(
        self, context: ToolExecutionContext, name: str, version: str, arguments: dict
    ) -> ToolResult | None:
        if not context.idempotency_key:
            raise ValueError("Tool Calls require an idempotency key")
        request = {"name": name, "version": version, "arguments": arguments}
        request_hash = hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        now = datetime.now(timezone.utc)
        async with self._sessions() as session:
            session.add(
                ToolExecutionRow(
                    id=uuid4().hex,
                    user_id=context.user_id,
                    run_id=context.run_id,
                    call_id=context.call_id,
                    idempotency_key=context.idempotency_key,
                    request_hash=request_hash,
                    tool_name=name,
                    tool_version=version,
                    arguments=redact_secrets(arguments),
                    status="running",
                    created_at=now,
                    updated_at=now,
                )
            )
            try:
                await session.commit()
                return None
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(ToolExecutionRow).where(
                        ToolExecutionRow.user_id == context.user_id,
                        ToolExecutionRow.idempotency_key == context.idempotency_key,
                    )
                )
                if existing is None:
                    raise
                if existing.request_hash != request_hash:
                    raise IdempotencyConflict("Tool idempotency key was reused for different input")
                if existing.result is not None:
                    return ToolResult(**existing.result)
                return ToolResult(
                    context.call_id, name, "running", error="Tool Call is already in progress"
                )

    async def finish_tool_call(self, context: ToolExecutionContext, result: ToolResult) -> None:
        payload = redact_secrets(
            {
                "call_id": result.call_id,
                "name": result.name,
                "status": result.status,
                "output": dict(result.output),
                "error": result.error,
                "duration_ms": result.duration_ms,
            }
        )
        async with self._sessions() as session:
            row = await session.scalar(
                select(ToolExecutionRow).where(
                    ToolExecutionRow.user_id == context.user_id,
                    ToolExecutionRow.idempotency_key == context.idempotency_key,
                ).with_for_update()
            )
            if row is None:
                raise LookupError("Tool execution audit record not found")
            if row.call_id != context.call_id or row.run_id != context.run_id:
                raise IdempotencyConflict("Tool execution identity does not match its audit record")
            row.status = result.status
            row.result = payload
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()


__all__ = ["PostgresToolExecutionRepository", "ToolExecutionRow"]
