"""Transactional alert ingestion and investigation deduplication."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agent_server.alertmanager import NormalizedAlert
from agent_server.ingest.fingerprint import alert_fingerprint, delivery_key
from agent_server.persistence.postgres import AlertRow, AuditLogRow, InvestigationRow


logger = logging.getLogger(__name__)
OPEN_STATUSES = ("pending", "running", "completed", "completed_degraded")


@dataclass(frozen=True)
class IngestResult:
    alert_id: str
    investigation_id: str | None
    action: Literal["created", "deduped", "resolved", "ignored"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "investigation_id": self.investigation_id,
            "action": self.action,
        }


def _cooldown_seconds() -> int:
    try:
        return max(0, int(os.getenv("DEDUP_COOLDOWN_SECONDS", "300")))
    except ValueError:
        return 300


def _extra_labels() -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.getenv("DEDUP_EXTRA_LABELS", "").split(",")
        if item.strip()
    )


def _audit(
    session: Any,
    *,
    action: str,
    object_type: str,
    object_id: str,
    details: dict[str, Any],
    ts: datetime,
) -> None:
    session.add(
        AuditLogRow(
            ts=ts,
            actor="alertmanager",
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details,
        )
    )


async def _active_investigation(session: Any, owner_user_id: str, fingerprint: str) -> InvestigationRow | None:
    return await session.scalar(
        select(InvestigationRow)
        .where(
            InvestigationRow.owner_user_id == owner_user_id,
            InvestigationRow.fingerprint == fingerprint,
            InvestigationRow.status.in_(OPEN_STATUSES),
        )
        .order_by(InvestigationRow.created_at.desc())
        .with_for_update()
    )


async def _insert_alert(
    session: Any, alert: NormalizedAlert, fingerprint: str
) -> tuple[AlertRow | None, bool]:
    key = delivery_key(alert)
    statement = (
        pg_insert(AlertRow)
        .values(
            id=uuid4().hex,
            owner_user_id=alert.owner_user_id,
            fingerprint=fingerprint,
            delivery_key=key,
            source=alert.source,
            source_fingerprint=alert.source_fingerprint,
            alertname=alert.alertname,
            severity=alert.severity,
            status=alert.status,
            namespace=alert.namespace,
            workload=alert.workload,
            pod=alert.pod,
            summary=alert.summary,
            description=alert.description,
            labels=alert.labels,
            annotations=alert.annotations,
            raw=alert.raw,
            started_at=alert.started_at,
            ended_at=alert.ended_at,
            received_at=alert.received_at,
        )
        .on_conflict_do_nothing(index_elements=["delivery_key"])
        .returning(AlertRow.id)
    )
    inserted_id = (await session.execute(statement)).scalar_one_or_none()
    if inserted_id is None:
        return await session.scalar(select(AlertRow).where(AlertRow.delivery_key == key)), False
    return await session.scalar(select(AlertRow).where(AlertRow.id == inserted_id)), True


async def _create_investigation(
    session: Any, alert: NormalizedAlert, fingerprint: str, now: datetime
) -> InvestigationRow:
    investigation = InvestigationRow(
        id=uuid4().hex,
        owner_user_id=alert.owner_user_id,
        fingerprint=fingerprint,
        status="pending",
        alertname=alert.alertname,
        namespace=alert.namespace,
        workload=alert.workload,
        severity=alert.severity,
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=1,
        attempt_count=0,
        max_attempts=3,
        run_after=now,
        created_at=now,
        updated_at=now,
    )
    statement = (
        pg_insert(InvestigationRow)
        .values(
            id=investigation.id,
            owner_user_id=investigation.owner_user_id,
            fingerprint=investigation.fingerprint,
            status=investigation.status,
            alertname=investigation.alertname,
            namespace=investigation.namespace,
            workload=investigation.workload,
            severity=investigation.severity,
            first_seen_at=investigation.first_seen_at,
            last_seen_at=investigation.last_seen_at,
            occurrence_count=investigation.occurrence_count,
            attempt_count=investigation.attempt_count,
            max_attempts=investigation.max_attempts,
            run_after=investigation.run_after,
            created_at=investigation.created_at,
            updated_at=investigation.updated_at,
        )
        .on_conflict_do_nothing(
            index_elements=["fingerprint"],
            index_where=text(
                "status IN ('pending', 'running', 'completed', 'completed_degraded')"
            ),
        )
        .returning(InvestigationRow.id)
    )
    inserted_id = (await session.execute(statement)).scalar_one_or_none()
    if inserted_id is None:
        existing = await _active_investigation(session, alert.owner_user_id, fingerprint)
        if existing is None:
            raise RuntimeError("investigation insert raced without an active row")
        return existing
    return investigation


async def _ingest_one(session: Any, alert: NormalizedAlert) -> IngestResult:
    now = alert.received_at.astimezone(timezone.utc)
    fingerprint = alert_fingerprint(alert, _extra_labels())
    stored_alert, inserted = await _insert_alert(session, alert, fingerprint)
    if stored_alert is None:
        raise RuntimeError("alert insert returned no row")

    # Exact duplicate delivery is idempotent and must not increment occurrence_count.
    if not inserted:
        existing_investigation = (
            await session.scalar(
                select(InvestigationRow).where(
                    InvestigationRow.id == stored_alert.investigation_id
                )
            )
            if stored_alert.investigation_id
            else None
        )
        await session.commit()
        return IngestResult(
            stored_alert.id,
            existing_investigation.id if existing_investigation else stored_alert.investigation_id,
            "deduped",
        )

    active = await _active_investigation(session, alert.owner_user_id, fingerprint)
    if alert.status == "resolved":
        if active is None:
            await session.commit()
            return IngestResult(stored_alert.id, None, "ignored")
        active.resolved_at = alert.ended_at or now
        active.last_seen_at = now
        active.updated_at = now
        if active.status != "running":
            active.status = "closed"
        stored_alert.investigation_id = active.id
        _audit(
            session,
            action="investigation_resolved",
            object_type="investigation",
            object_id=active.id,
            details={"fingerprint": fingerprint, "status": active.status},
            ts=now,
        )
        await session.commit()
        return IngestResult(stored_alert.id, active.id, "resolved")

    if active is not None:
        active.occurrence_count += 1
        active.last_seen_at = now
        active.updated_at = now
        stored_alert.investigation_id = active.id
        _audit(
            session,
            action="alert_deduped",
            object_type="investigation",
            object_id=active.id,
            details={"fingerprint": fingerprint, "occurrence_count": active.occurrence_count},
            ts=now,
        )
        await session.commit()
        return IngestResult(stored_alert.id, active.id, "deduped")

    recent = await session.scalar(
        select(InvestigationRow)
        .where(
            InvestigationRow.fingerprint == fingerprint,
            InvestigationRow.owner_user_id == alert.owner_user_id,
            InvestigationRow.status == "closed",
            InvestigationRow.resolved_at.is_not(None),
            InvestigationRow.resolved_at
            >= now - timedelta(seconds=_cooldown_seconds()),
        )
        .order_by(InvestigationRow.resolved_at.desc())
        .with_for_update()
    )
    if recent is not None:
        recent.status = "pending"
        recent.resolved_at = None
        recent.last_seen_at = now
        recent.occurrence_count += 1
        recent.attempt_count = 0
        recent.locked_by = None
        recent.locked_at = None
        recent.run_after = now
        recent.updated_at = now
        stored_alert.investigation_id = recent.id
        _audit(
            session,
            action="investigation_reopened",
            object_type="investigation",
            object_id=recent.id,
            details={"fingerprint": fingerprint, "cooldown_seconds": _cooldown_seconds()},
            ts=now,
        )
        await session.commit()
        return IngestResult(stored_alert.id, recent.id, "deduped")

    investigation = await _create_investigation(session, alert, fingerprint, now)
    stored_alert.investigation_id = investigation.id
    _audit(
        session,
        action="investigation_created",
        object_type="investigation",
        object_id=investigation.id,
        details={"fingerprint": fingerprint, "alertname": alert.alertname},
        ts=now,
    )
    await session.commit()
    return IngestResult(stored_alert.id, investigation.id, "created")


async def ingest_alerts(session: Any, alerts: list[NormalizedAlert]) -> list[IngestResult]:
    """Persist alerts and enqueue at most one durable investigation per fingerprint."""

    results: list[IngestResult] = []
    for alert in alerts:
        results.append(await _ingest_one(session, alert))
    return results


__all__ = ["IngestResult", "ingest_alerts"]
