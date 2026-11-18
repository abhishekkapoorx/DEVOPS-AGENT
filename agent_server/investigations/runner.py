"""Phase D deterministic investigation runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from agent_server.alertmanager import NormalizedAlert
from agent_server.investigations.context import build_context_pack
from agent_server.investigations.analysis import analyze_context
from agent_server.investigations.llm import LLMClient, LLMBudget
from agent_server.investigations.registry import ToolRegistry
from agent_server.investigations.slack import SlackPoster, build_analyzed_briefing, build_deterministic_briefing
from agent_server.persistence.postgres import AlertRow, AuditLogRow, InvestigationRow, InvestigationRunRow
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
        llm_client: LLMClient | None = None,
        llm_budget: LLMBudget | None = None,
    ) -> None:
        self.sessions = sessions
        self.kube_factory = kube_factory
        self.slack = slack or SlackPoster()
        self.llm_client = llm_client
        self.llm_budget = llm_budget or LLMBudget()

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

        analyzed = None
        degraded_reason = None
        if self.llm_client is not None:
            try:
                analyzed = await analyze_context(pack, self.llm_client, budget=self.llm_budget)
                if analyzed.verifier.claims_kept == 0:
                    degraded_reason = "verifier dropped every model claim"
            except Exception as exc:
                degraded_reason = f"LLM analysis failed: {type(exc).__name__}"
        else:
            degraded_reason = "LLM analysis is not configured"

        async with self.sessions() as session:
            row = await session.scalar(
                select(InvestigationRow).where(InvestigationRow.id == investigation.id)
            )
            if row is not None:
                if analyzed is not None and degraded_reason is None:
                    row.result = {
                        "hypotheses": [item.model_dump() | {"confidence": confidence.level, "confidence_reasons": confidence.reasons} for item, confidence in analyzed.ranked],
                    }
                    row.verifier_report = analyzed.verifier.model_dump()
                    row.status = "completed"
                    session.add(
                        AuditLogRow(
                            ts=datetime.now(timezone.utc),
                            actor="investigation-worker",
                            action="llm_completed",
                            object_type="investigation",
                            object_id=row.id,
                            details={"model": analyzed.llm_result.model, "cost_usd": analyzed.llm_result.cost_usd},
                        )
                    )
                    session.add(
                        InvestigationRunRow(
                            investigation_id=row.id,
                            model=analyzed.llm_result.model,
                            prompt_hash=analyzed.prompt_hash,
                            tokens_in=analyzed.llm_result.tokens_in,
                            tokens_out=analyzed.llm_result.tokens_out,
                            cost_usd=analyzed.llm_result.cost_usd,
                            latency_ms=analyzed.llm_result.latency_ms,
                            tool_call_count=pack.tool_call_count,
                            outcome="completed",
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                else:
                    row.status = "completed_degraded"
                    row.result = {"fallback": "deterministic_context_pack", "reason": degraded_reason}
                    row.verifier_report = analyzed.verifier.model_dump() if analyzed else None
                    session.add(
                        AuditLogRow(
                            ts=datetime.now(timezone.utc),
                            actor="investigation-worker",
                            action="llm_degraded",
                            object_type="investigation",
                            object_id=row.id,
                            details={"reason": degraded_reason},
                        )
                    )
                    session.add(
                        InvestigationRunRow(
                            investigation_id=row.id,
                            model=analyzed.llm_result.model if analyzed else "none",
                            prompt_hash="",
                            tokens_in=analyzed.llm_result.tokens_in if analyzed else 0,
                            tokens_out=analyzed.llm_result.tokens_out if analyzed else 0,
                            cost_usd=analyzed.llm_result.cost_usd if analyzed else 0,
                            latency_ms=analyzed.llm_result.latency_ms if analyzed else 0,
                            tool_call_count=pack.tool_call_count,
                            outcome="degraded",
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                await session.commit()

        if investigation.slack_posted_at is None:
            if analyzed is not None and degraded_reason is None:
                message = build_analyzed_briefing(
                    pack,
                    analyzed.ranked,
                    analyzed.verifier,
                    occurrence_count=investigation.occurrence_count,
                )
                delivered = await self.slack.post_text(message) if self.slack.webhook_url else False
            else:
                message = build_deterministic_briefing(
                    pack,
                    occurrence_count=investigation.occurrence_count,
                    status="Degraded: deterministic context pack",
                    reason=degraded_reason,
                )
                delivered = await self.slack.post_text(message) if self.slack.webhook_url else False
                if not self.slack.webhook_url:
                    await self.slack.post(pack, occurrence_count=investigation.occurrence_count, status="Degraded: deterministic context pack", reason=degraded_reason)
            if delivered or not self.slack.webhook_url:
                async with self.sessions() as session:
                    row = await session.scalar(
                        select(InvestigationRow).where(InvestigationRow.id == investigation.id)
                    )
                    if row is not None:
                        row.slack_posted_at = datetime.now(timezone.utc)
                        session.add(
                            AuditLogRow(
                                ts=row.slack_posted_at,
                                actor="investigation-worker",
                                action="slack_posted",
                                object_type="investigation",
                                object_id=row.id,
                                details={"delivered": delivered},
                            )
                        )
                        await session.commit()


__all__ = ["InvestigationRunner"]
