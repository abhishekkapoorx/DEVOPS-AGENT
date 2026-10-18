"""Lease-based worker for durable, restartable Agent Runs."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from agent_core import AgentRequest, AgentRuntime
from agent_core.conversations import ConversationRepository
from agent_core.runs import AgentRun, RunLeaseLost, RunRepository

logger = logging.getLogger(__name__)


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
    ) -> None:
        if lease_seconds < 3 or poll_interval <= 0 or max_concurrency < 1:
            raise ValueError("invalid Agent Run worker limits")
        self.runtime = runtime
        self.conversations = conversations
        self.runs = runs
        self.worker_id = worker_id or uuid4().hex
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self.max_concurrency = max_concurrency
        self._active: set[asyncio.Task] = set()

    async def run_once(self) -> bool:
        run = await self.runs.claim_next_run(self.worker_id, self.lease_seconds)
        if run is None:
            return False
        await self._execute(run)
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
            task = asyncio.create_task(self._execute(run))
            self._active.add(task)

        if self._active:
            await asyncio.gather(*self._active, return_exceptions=True)

    async def _execute(self, run: AgentRun) -> None:
        heartbeat = asyncio.create_task(self._renew_lease(run.id))
        try:
            all_messages = await self.conversations.list_messages(
                run.user_id, run.conversation_id
            )
            history = _history_before_message(all_messages, run.message_id)
            result = await self.runtime.run(
                AgentRequest(
                    user_id=run.user_id,
                    conversation_id=run.conversation_id,
                    run_id=run.id,
                    message=run.input_message,
                    history=tuple(
                        {"role": item.role, "content": item.content} for item in history
                    ),
                )
            )
            calls = [
                {"call_id": call.call_id, "name": call.name, "arguments": dict(call.arguments)}
                for call in result.tool_calls
            ]
            await self.runs.complete_run(
                run.user_id, run.id, self.worker_id, result.message, calls
            )
        except RunLeaseLost:
            # The lease expired and another worker owns the retry.
            return
        except Exception:
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


__all__ = ["AgentRunWorker"]
