"""Durable agent-run contracts shared by API and persistence adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Mapping, Protocol, Sequence


RunState = Literal[
    "pending", "running", "waiting_for_approval", "completed", "failed", "cancelled", "expired"
]


@dataclass(frozen=True)
class AgentRun:
    id: str
    user_id: str
    conversation_id: str
    idempotency_key: str
    request_hash: str
    message_id: str
    input_message: str
    state: RunState
    attempt: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    message: str = ""
    tool_calls: tuple[Mapping[str, object], ...] = ()
    error: str | None = None
    correlation_id: str = ""
    traceparent: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    run_id: str
    event_type: str
    data: Mapping[str, object]
    created_at: datetime


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for a different request body."""


class RunLeaseLost(RuntimeError):
    """A worker attempted to finalize a run after its lease had moved."""


class RunRepository(Protocol):
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
    ) -> tuple[AgentRun, bool]: ...

    async def claim_next_run(self, worker_id: str, lease_seconds: int) -> AgentRun | None: ...

    async def renew_run_lease(self, worker_id: str, run_id: str, lease_seconds: int) -> bool: ...

    async def complete_run(
        self,
        user_id: str,
        run_id: str,
        worker_id: str,
        message: str,
        tool_calls: Sequence[Mapping[str, object]],
    ) -> AgentRun: ...

    async def fail_run(
        self, user_id: str, run_id: str, worker_id: str, error: str
    ) -> AgentRun: ...

    async def cancel_run(self, user_id: str, run_id: str) -> AgentRun | None: ...

    async def get_run(self, user_id: str, run_id: str) -> AgentRun | None: ...

    async def list_run_events(
        self, user_id: str, run_id: str, after: int = 0
    ) -> Sequence[RunEvent]: ...


__all__ = [
    "AgentRun", "IdempotencyConflict", "RunEvent", "RunLeaseLost", "RunRepository", "RunState"
]
