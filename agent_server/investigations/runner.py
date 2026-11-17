"""Phase D deterministic investigation runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from agent_server.alertmanager import NormalizedAlert
from agent_server.investigations.context import build_context_pack
from agent_server.investigations.registry import ToolRegistry
from agent_server.investigations.slack import SlackPoster
from agent_server.persistence.postgres import AlertRow, InvestigationRow
from agent_server.tools.collectors.kubernetes_tools import default_kubernetes_tools


async def _default_kube_factory():
    from agent_server.tools.collectors.kubernetes import ReadOnlyKube

    return await ReadOnlyKube.from_environment()


class InvestigationRunner:
    """Build deterministic evidence and post the permanent fallback briefing."""

    def __init__(
        self,
        sessions: Any,
        *,
        kube_factory: Callable[[], Awaitable[Any]] = _default_kube_factory,
        slack: SlackPoster | None = None,
    ) -> None:
        self.sessions = sessions
        self.kube_factory = kube_factory
        self.slack = slack or SlackPoster()

    async def __call__(self, investigation: InvestigationRow) -> None:
        async with self.sessions() as session:
            alert_row = await session.scalar(
                select(AlertRow)
                .where(AlertRow.investigation_id == investigation.id)
                .order_by(AlertRow.received_at.desc())
            )
            if alert_row is None:
                raise RuntimeError("investigation has no alert")
            alert = NormalizedAlert(
                source=alert_row.source,
                source_fingerprint=alert_row.source_fingerprint,
                alertname=alert_row.alertname,
                severity=alert_row.severity,
                status=alert_row.status,
                namespace=alert_row.namespace,
                workload=alert_row.workload,
                pod=alert_row.pod,
                summary=alert_row.summary,
                description=alert_row.description,
                labels=alert_row.labels,
                annotations=alert_row.annotations,
                started_at=alert_row.started_at,
                ended_at=alert_row.ended_at,
                received_at=alert_row.received_at,
                raw=alert_row.raw,
            )
            try:
                kube = await self.kube_factory()
                tools = default_kubernetes_tools(kube)
            except Exception:
                tools = []
            registry = ToolRegistry(tools, session)
            pack = await build_context_pack(alert, investigation.id, registry)
            await session.commit()

        if investigation.slack_posted_at is None:
            delivered = await self.slack.post(
                pack,
                occurrence_count=investigation.occurrence_count,
            )
            if delivered or not self.slack.webhook_url:
                async with self.sessions() as session:
                    row = await session.scalar(
                        select(InvestigationRow).where(InvestigationRow.id == investigation.id)
                    )
                    if row is not None:
                        row.slack_posted_at = datetime.now(timezone.utc)
                        await session.commit()


__all__ = ["InvestigationRunner"]
