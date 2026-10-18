"""Lease-based worker for durable, restartable Agent Runs."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4
from typing import Any, Callable, Protocol

from agent_core import AgentRequest, AgentRuntime, AgentToolCall
from agent_core.conversations import ConversationRepository
from agent_core.runs import AgentRun, RunLeaseLost, RunRepository
from agent_core.tools import ToolExecutionContext, ToolResult
from agent_protocol import redact_secrets

logger = logging.getLogger(__name__)


class ToolExecutor(Protocol):
    async def execute(
        self, *, name: str, version: str, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> ToolResult: ...


class AgentRunWorker:
    """Claims persisted runs from PostgreSQL and resumes expired leases."""

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        conversations: ConversationRepository,
        runs: RunRepository,
        worker_id: str | None = None,
        lease_seconds: int = 60,
        poll_interval: float = 0.5,
        max_concurrency: int = 4,
        tool_executor: ToolExecutor | None = None,
        max_tool_rounds: int = 8,
        tool_scopes_for_user: Callable[[str], frozenset[str]] = lambda _user_id: frozenset(),
    ) -> None:
        if lease_seconds < 3 or poll_interval <= 0 or max_concurrency < 1 or max_tool_rounds < 1:
            raise ValueError("invalid Agent Run worker limits")
        self.runtime = runtime
        self.conversations = conversations
        self.runs = runs
        self.worker_id = worker_id or uuid4().hex
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self.max_concurrency = max_concurrency
        self.tool_executor = tool_executor
        self.max_tool_rounds = max_tool_rounds
        self.tool_scopes_for_user = tool_scopes_for_user
        self._active: set[asyncio.Task] = set()
        self._run_tasks: dict[str, asyncio.Task] = {}

    async def run_once(self) -> bool:
        run = await self.runs.claim_next_run(self.worker_id, self.lease_seconds)
        if run is None:
            return False
        await self._execute_tracked(run)
        return True

    def cancel(self, run_id: str) -> bool:
        task = self._run_tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def run_forever(self, stopping: asyncio.Event) -> None:
        while not stopping.is_set():
            self._active = {task for task in self._active if not task.done()}
            if len(self._active) >= self.max_concurrency:
                await asyncio.sleep(self.poll_interval)
                continue
            try:
                run = await self.runs.claim_next_run(self.worker_id, self.lease_seconds)
            except Exception:
                logger.exception("Unable to claim an Agent Run")
                await asyncio.sleep(self.poll_interval)
                continue
            if run is None:
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=self.poll_interval)
                except TimeoutError:
                    pass
                continue
            task = asyncio.create_task(self._execute_tracked(run))
            self._active.add(task)

        if self._active:
            await asyncio.gather(*self._active, return_exceptions=True)

    async def _execute_tracked(self, run: AgentRun) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._run_tasks[run.id] = task
        try:
            await self._execute(run)
        finally:
            if task is not None and self._run_tasks.get(run.id) is task:
                self._run_tasks.pop(run.id, None)

    async def _execute(self, run: AgentRun) -> None:
        heartbeat = asyncio.create_task(self._renew_lease(run.id))
        try:
            all_messages = await self.conversations.list_messages(
                run.user_id, run.conversation_id
            )
            history = _history_before_message(all_messages, run.message_id)
            persisted_history = tuple(
                {"role": item.role, "content": item.content} for item in history
            )
            tool_results: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            for _round in range(self.max_tool_rounds):
                result = await self.runtime.run(
                    AgentRequest(
                        user_id=run.user_id,
                        conversation_id=run.conversation_id,
                        run_id=run.id,
                        message=run.input_message,
                        history=persisted_history,
                        tool_results=tuple(tool_results),
                        correlation_id=run.correlation_id,
                        traceparent=run.traceparent,
                    )
                )
                if not result.tool_calls:
                    await self.runs.complete_run(
                        run.user_id, run.id, self.worker_id, result.message, tool_calls
                    )
                    return
                if self.tool_executor is None:
                    raise RuntimeError("Registered Tool Service is not configured")
                for call in result.tool_calls:
                    tool_result = await self.tool_executor.execute(
                        name=call.name,
                        version=call.version,
                        arguments=dict(call.arguments),
                        context=_tool_context(
                            run, call, self.tool_scopes_for_user(run.user_id)
                        ),
                    )
                    serialized_result = redact_secrets({
                        "call_id": tool_result.call_id,
                        "name": tool_result.name,
                        "status": tool_result.status,
                        "output": dict(tool_result.output),
                        "error": tool_result.error,
                    })
                    tool_calls.append(
                        {
                            "call_id": call.call_id,
                            "name": call.name,
                            "version": call.version,
                            "arguments": redact_secrets(dict(call.arguments)),
                            "result": serialized_result,
                        }
                    )
                    tool_results.append(serialized_result)
            raise RuntimeError("Agent exceeded the configured Tool Call round limit")
        except RunLeaseLost:
            # The lease expired and another worker owns the retry.
            return
        except Exception as exc:
            # Keep the client-facing run error generic, but preserve a sanitized
            # diagnostic in API logs so provider/configuration failures can be
            # distinguished from persistence and tool-service failures.
            logger.error(
                "Agent Run %s failed (%s): %s",
                run.id,
                type(exc).__name__,
                redact_secrets(str(exc)),
            )
            try:
                await self.runs.fail_run(
                    run.user_id, run.id, self.worker_id, "Agent runtime failed"
                )
            except (LookupError, RunLeaseLost):
                return
            except Exception:
                logger.exception("Unable to record Agent Run failure for %s", run.id)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _renew_lease(self, run_id: str) -> None:
        interval = max(1, self.lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            try:
                if not await self.runs.renew_run_lease(
                    self.worker_id, run_id, self.lease_seconds
                ):
                    return
            except Exception:
                logger.exception("Unable to renew Agent Run lease %s", run_id)


def _history_before_message(messages, message_id: str):
    history = []
    for item in messages:
        if item.id == message_id:
            return history
        history.append(item)
    raise LookupError("current run message is missing from conversation history")


def _tool_context(
    run: AgentRun, call: AgentToolCall, scopes: frozenset[str]
) -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id=run.user_id,
        run_id=run.id,
        call_id=call.call_id,
        scopes=scopes,
        correlation_id=run.correlation_id or run.id,
        idempotency_key=f"{run.id}:{call.call_id}",
        traceparent=run.traceparent,
    )


__all__ = ["AgentRunWorker", "ToolExecutor"]
