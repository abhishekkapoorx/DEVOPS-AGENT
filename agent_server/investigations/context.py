"""Deterministic context-pack collection plan."""

from __future__ import annotations

from agent_server.alertmanager import NormalizedAlert
from agent_server.investigations.evidence import ContextPack
from agent_server.investigations.registry import CollectorArgs, ToolRegistry


async def build_context_pack(
    alert: NormalizedAlert,
    investigation_id: str,
    registry: ToolRegistry,
) -> ContextPack:
    args = CollectorArgs(
        investigation_id=investigation_id,
        namespace=alert.namespace,
        workload=alert.workload,
        pod=alert.pod,
        container=alert.container,
        service=alert.service,
    )
    evidence = []
    errors: list[dict[str, str]] = []
    for name in (
        "kubernetes.pod_status",
        "kubernetes.events",
        "kubernetes.logs",
        "kubernetes.rollout_history",
        "kubernetes.endpoints",
        "kubernetes.namespace_overview",
    ):
        try:
            evidence.extend(await registry.run(name, args))
        except Exception as exc:
            errors.append({"tool": name, "error": type(exc).__name__})
    return ContextPack(
        investigation_id=investigation_id,
        alertname=alert.alertname,
        namespace=alert.namespace,
        workload=alert.workload,
        severity=alert.severity,
        summary=alert.summary,
        evidence=evidence,
        collection_errors=errors,
        tool_call_count=registry.call_count,
    )


__all__ = ["build_context_pack"]
