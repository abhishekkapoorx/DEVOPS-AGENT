"""Process-local conversation adapter for development and isolated tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agent_core.conversations import Conversation, ConversationMessage
from agent_core.runs import AgentRun, IdempotencyConflict, RunEvent, RunLeaseLost


class InMemoryConversationRepository:
    """A concurrency-safe adapter; production deployments must inject durable storage."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[ConversationMessage]] = {}
        self._runs: dict[str, AgentRun] = {}
        self._run_keys: dict[tuple[str, str, str], str] = {}
        self._run_events: dict[str, list[RunEvent]] = {}

    async def health_check(self) -> bool:
        return True

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

    async def rename(self, user_id: str, conversation_id: str, title: str) -> Conversation | None:
        async with self._lock:
            item = self._conversations.get(conversation_id)
            if item is None or item.user_id != user_id:
                return None
            renamed = replace(item, title=title, updated_at=datetime.now(timezone.utc))
            self._conversations[conversation_id] = renamed
            return renamed

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
        key = (user_id, conversation_id, idempotency_key)
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None or conversation.user_id != user_id:
                raise LookupError("conversation not found")
            existing_id = self._run_keys.get(key)
            if existing_id is not None:
                existing = self._runs[existing_id]
                if existing.request_hash != request_hash:
                    raise IdempotencyConflict("Idempotency-Key was already used for another message")
                return existing, False

            message = ConversationMessage(
                uuid4().hex, conversation_id, "user", content, now
            )
            run = AgentRun(
                id=uuid4().hex,
                user_id=user_id,
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                message_id=message.id,
                input_message=content,
                state="pending",
                correlation_id=correlation_id,
                traceparent=traceparent,
                created_at=now,
                updated_at=now,
            )
            self._messages[conversation_id].append(message)
            self._conversations[conversation_id] = replace(conversation, updated_at=now)
            self._runs[run.id] = run
            self._run_keys[key] = run.id
            self._run_events[run.id] = []
            self._append_run_event(run, "created", {"state": "pending"}, now)
            return run, True

    async def claim_next_run(self, worker_id: str, lease_seconds: int) -> AgentRun | None:
        async with self._lock:
            now = datetime.now(timezone.utc)
            candidates = sorted(self._runs.values(), key=lambda run: run.created_at)
            for run in candidates:
                expired = run.lease_expires_at is not None and run.lease_expires_at <= now
                if run.state != "pending" and not (run.state == "running" and expired):
                    continue
                prior_attempt = run.attempt
                run = replace(
                    run,
                    state="running",
                    attempt=prior_attempt + 1,
                    lease_owner=worker_id,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
                self._runs[run.id] = run
                event_type = "running" if prior_attempt == 0 else "resumed"
                self._append_run_event(run, event_type, {"state": "running", "attempt": run.attempt}, now)
                return run
            return None

    async def renew_run_lease(self, worker_id: str, run_id: str, lease_seconds: int) -> bool:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.state != "running" or run.lease_owner != worker_id:
                return False
            now = datetime.now(timezone.utc)
            self._runs[run_id] = replace(
                run, lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now
            )
            return True

    async def append_run_event(self, user_id, run_id, worker_id, event_type, data):
        async with self._lock:
            run = self._owned_run(user_id, run_id)
            if run.lease_owner != worker_id or run.state != "running":
                raise RunLeaseLost("run lease is no longer owned by this worker")
            now = datetime.now(timezone.utc)
            self._append_run_event(run, event_type, dict(data), now)
            return self._run_events[run_id][-1]

    async def complete_run(
        self,
        user_id: str,
        run_id: str,
        worker_id: str,
        message: str,
        tool_calls,
    ) -> AgentRun:
        async with self._lock:
            run = self._owned_run(user_id, run_id)
            if run.lease_owner != worker_id:
                raise RunLeaseLost("run lease is no longer owned by this worker")
            if run.state != "completed":
                now = datetime.now(timezone.utc)
                calls = tuple(dict(call) for call in tool_calls)
                run = replace(
                    run,
                    state="completed",
                    message=message,
                    tool_calls=calls,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
                self._runs[run_id] = run
                if message:
                    self._messages[run.conversation_id].append(
                        ConversationMessage(
                            uuid4().hex, run.conversation_id, "assistant", message, now
                        )
                    )
                self._append_run_event(
                    run,
                    "completed",
                    {"state": "completed", "message": message, "tool_calls": list(calls)},
                    now,
                )
            return run

    async def fail_run(self, user_id: str, run_id: str, worker_id: str, error: str) -> AgentRun:
        async with self._lock:
            run = self._owned_run(user_id, run_id)
            if run.lease_owner != worker_id:
                raise RunLeaseLost("run lease is no longer owned by this worker")
            if run.state not in {"completed", "failed"}:
                now = datetime.now(timezone.utc)
                run = replace(
                    run, state="failed", error=error, lease_owner=None,
                    lease_expires_at=None, updated_at=now
                )
                self._runs[run_id] = run
                self._append_run_event(run, "failed", {"state": "failed", "error": error}, now)
            return run

    async def cancel_run(self, user_id: str, run_id: str) -> AgentRun | None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.user_id != user_id:
                return None
            if run.state in {"completed", "failed", "cancelled", "expired"}:
                return run
            now = datetime.now(timezone.utc)
            cancelled = replace(
                run,
                state="cancelled",
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
            )
            self._runs[run_id] = cancelled
            self._append_run_event(cancelled, "cancelled", {"state": "cancelled"}, now)
            return cancelled

    async def get_run(self, user_id: str, run_id: str) -> AgentRun | None:
        async with self._lock:
            run = self._runs.get(run_id)
            return run if run and run.user_id == user_id else None

    async def list_run_events(self, user_id: str, run_id: str, after: int = 0):
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.user_id != user_id:
                return ()
            return tuple(event for event in self._run_events[run_id] if event.sequence > after)

    def _owned_run(self, user_id: str, run_id: str) -> AgentRun:
        run = self._runs.get(run_id)
        if run is None or run.user_id != user_id:
            raise LookupError("run not found")
        return run

    def _append_run_event(self, run: AgentRun, event_type: str, data, created_at) -> None:
        events = self._run_events[run.id]
        events.append(RunEvent(len(events) + 1, run.id, event_type, data, created_at))


__all__ = ["InMemoryConversationRepository"]
