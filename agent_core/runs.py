"""Durable agent-run contracts shared by API and persistence adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Mapping, Protocol, Sequence


RunState = Literal[
    "pending", "running", "waiting_for_approval", "completed", "failed", "cancelled", "expired"
]

MAX_CONVERSATION_EVENT_OUTPUT_CHARS = 16_000


def bounded_conversation_event_data(event_type: str, data: Mapping[str, object]) -> dict[str, object]:
    """Keep execution results copied into the timeline bounded for storage and retrieval."""
    result = dict(data)
    tool_result = result.get("result")
    if isinstance(tool_result, dict):
        if event_type == "tool_call_completed":
            output = tool_result.get("output")
            if output is not None:
                bounded_output = _bounded_value(output)
                result["result"] = {**tool_result, "output": bounded_output}
            error = tool_result.get("error")
            if isinstance(error, str) and len(error) > MAX_CONVERSATION_EVENT_OUTPUT_CHARS:
                result["result"]["error"] = (
                    error[:MAX_CONVERSATION_EVENT_OUTPUT_CHARS] + " … [truncated]"
                )
        elif event_type in {"subagent_update", "subagent_completed", "graph_step"}:
            result["result"] = _bounded_value(tool_result)
    if event_type == "completed" and isinstance(result.get("tool_calls"), list):
        result["tool_calls"] = [_bounded_value(call) for call in result["tool_calls"]]
    return result


def _bounded_value(value: object) -> object:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(serialized) > MAX_CONVERSATION_EVENT_OUTPUT_CHARS:
        return {
            "preview": serialized[:MAX_CONVERSATION_EVENT_OUTPUT_CHARS],
            "truncated": True,
            "original_chars": len(serialized),
        }
    return value


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


@dataclass(frozen=True)
class ConversationEvent:
    sequence: int
    id: str
    conversation_id: str
    run_id: str | None
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

    async def append_run_event(
        self, user_id: str, run_id: str, worker_id: str, event_type: str,
        data: Mapping[str, object],
    ) -> RunEvent: ...

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

    async def list_conversation_events(
        self, user_id: str, conversation_id: str, after: int = 0, limit: int = 100
    ) -> Sequence[ConversationEvent]: ...


__all__ = [
    "AgentRun", "ConversationEvent", "IdempotencyConflict", "RunEvent", "RunLeaseLost",
    "RunRepository", "RunState", "MAX_CONVERSATION_EVENT_OUTPUT_CHARS",
    "bounded_conversation_event_data",
]
