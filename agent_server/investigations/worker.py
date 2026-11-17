"""Postgres-backed durable investigation queue worker."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select

from agent_server.persistence.postgres import AuditLogRow, InvestigationRow


logger = logging.getLogger(__name__)
InvestigationHandler = Callable[[InvestigationRow], Awaitable[None]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def backoff_seconds(attempt_count: int) -> int:
    return min(300, 2 ** max(0, attempt_count - 1))


class InvestigationWorker:
    """Claim and execute one investigation at a time with a renewable lease."""

    def __init__(
        self,
        sessions: Any,
        handler: InvestigationHandler | None = None,
        *,
        worker_id: str | None = None,
        lease_seconds: int | None = None,
        poll_seconds: float | None = None,
    ) -> None:
        self._sessions = sessions
        self._handler = handler or self._complete_without_work
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.lease_seconds = lease_seconds or int(os.getenv("WORKER_LEASE_SECONDS", "60"))
        self.poll_seconds = poll_seconds or float(os.getenv("WORKER_POLL_SECONDS", "1"))

    async def _complete_without_work(self, _investigation: InvestigationRow) -> None:
        """Phase B handler; Phase C supplies evidence collection."""

    async def claim_one(self) -> InvestigationRow | None:
        now = _utcnow()
        reclaim_before = now - timedelta(seconds=self.lease_seconds)
        async with self._sessions() as session:
            row = await session.scalar(
                select(InvestigationRow)
                .where(
                    or_(
                        (InvestigationRow.status == "pending")
                        & (InvestigationRow.run_after <= now),
                        (InvestigationRow.status == "running")
                        & (InvestigationRow.locked_at <= reclaim_before),
                    )
                )
                .order_by(InvestigationRow.run_after, InvestigationRow.created_at)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            row.status = "running"
            row.locked_by = self.worker_id
            row.locked_at = now
            row.attempt_count += 1
            row.updated_at = now
            session.add(
                AuditLogRow(
                    ts=now,
                    actor=self.worker_id,
                    action="investigation_claimed",
                    object_type="investigation",
                    object_id=row.id,
                    details={"attempt_count": row.attempt_count},
                )
            )
            await session.commit()
            return row

    async def heartbeat(self, investigation_id: str, stopping: asyncio.Event) -> None:
        interval = max(1, self.lease_seconds // 3)
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass
            async with self._sessions() as session:
                row = await session.scalar(
                    select(InvestigationRow).where(
                        InvestigationRow.id == investigation_id,
                        InvestigationRow.status == "running",
                        InvestigationRow.locked_by == self.worker_id,
                    )
                )
                if row is None:
                    return
                row.locked_at = _utcnow()
                row.updated_at = row.locked_at
                await session.commit()

    async def _complete(self, investigation_id: str) -> None:
        now = _utcnow()
        async with self._sessions() as session:
            row = await session.scalar(
                select(InvestigationRow).where(
                    InvestigationRow.id == investigation_id,
                    InvestigationRow.locked_by == self.worker_id,
                )
            )
            if row is None:
                return
            row.status = "closed" if row.resolved_at is not None else "completed"
            row.locked_by = None
            row.locked_at = None
            row.updated_at = now
            session.add(
                AuditLogRow(
                    ts=now,
                    actor=self.worker_id,
                    action="investigation_completed",
                    object_type="investigation",
                    object_id=row.id,
                    details={"status": row.status},
                )
            )
            await session.commit()

    async def _fail(self, investigation_id: str, error: str) -> None:
        now = _utcnow()
        async with self._sessions() as session:
            row = await session.scalar(
                select(InvestigationRow).where(
                    InvestigationRow.id == investigation_id,
                    InvestigationRow.locked_by == self.worker_id,
                )
            )
            if row is None:
                return
            terminal = row.attempt_count >= row.max_attempts
            row.status = "failed" if terminal else "pending"
            row.run_after = now + timedelta(seconds=backoff_seconds(row.attempt_count))
            row.last_error = error[:4000]
            row.locked_by = None
            row.locked_at = None
            row.updated_at = now
            session.add(
                AuditLogRow(
                    ts=now,
                    actor=self.worker_id,
                    action="investigation_failed",
                    object_type="investigation",
                    object_id=row.id,
                    details={
                        "attempt_count": row.attempt_count,
                        "terminal": terminal,
                    },
                )
            )
            await session.commit()

    async def run_once(self) -> bool:
        investigation = await self.claim_one()
        if investigation is None:
            return False
        stopping = asyncio.Event()
        heartbeat_task = asyncio.create_task(self.heartbeat(investigation.id, stopping))
        try:
            await self._handler(investigation)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._fail(investigation.id, str(exc))
            logger.exception("investigation failed", extra={"investigation_id": investigation.id})
        else:
            await self._complete(investigation.id)
        finally:
            stopping.set()
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        return True

    async def run_forever(self, stopping: asyncio.Event) -> None:
        while not stopping.is_set():
            try:
                claimed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("investigation worker loop failed")
                claimed = False
            if not claimed:
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=self.poll_seconds)
                except asyncio.TimeoutError:
                    pass


__all__ = ["InvestigationWorker", "backoff_seconds"]
