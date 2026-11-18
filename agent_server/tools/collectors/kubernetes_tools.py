"""Deterministic Kubernetes evidence collectors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent_server.alertmanager import NormalizedAlert
from agent_server.investigations.evidence import Evidence
from agent_server.investigations.registry import CollectorArgs
from agent_server.investigations.redaction import redact
from agent_server.tools.collectors.kubernetes import ReadOnlyKube


def _evidence(args: CollectorArgs, source: str, query: str, summary: str, raw: Any, *, truncated=False) -> Evidence:
    return Evidence(
        investigation_id=args.investigation_id,
        source=source,
        query=query,
        fetched_at=datetime.now(timezone.utc),
        summary=summary,
        raw_ref=f"evidence:{args.investigation_id}:{source}",
        raw=redact(raw),
        truncated=truncated,
    )


def _ready_pods(pods: list[dict[str, Any]]) -> int:
    return sum(
        1
        for pod in pods
        for condition in pod.get("status", {}).get("conditions", [])
        if condition.get("type") == "Ready" and condition.get("status") == "True"
    )


class PodStatusTool:
    name = "kubernetes.pod_status"
    description = "Read pod phase, conditions, container states, restarts, and resources."
    args_schema = CollectorArgs

    def __init__(self, kube: ReadOnlyKube) -> None:
        self.kube = kube

    async def run(self, args: CollectorArgs) -> list[Evidence]:
        if not args.namespace:
            return []
        pod_name = args.pod
        if not pod_name and args.workload:
            pods = await self.kube.list_pods(args.namespace, f"app={args.workload}")
            pod_name = pods[0].get("metadata", {}).get("name") if pods else None
        if not pod_name:
            return []
        pod = await self.kube.read_pod(args.namespace, pod_name)
        status = pod.get("status", {})
        phase = status.get("phase", "Unknown")
        containers = status.get("container_statuses", [])
        reasons = [
            item.get("state", {}).get("waiting", {}).get("reason")
            or item.get("last_state", {}).get("terminated", {}).get("reason")
            for item in containers
        ]
        summary = f"pod {pod_name} phase={phase}; reasons={','.join(item for item in reasons if item) or 'none'}; restarts={sum(item.get('restart_count', 0) for item in containers)}"
        return [_evidence(args, self.name, f"pod/{args.namespace}/{pod_name}", summary, pod)]


class PodEventsTool:
    name = "kubernetes.events"
    description = "Read pod and namespace events in chronological order."
    args_schema = CollectorArgs

    def __init__(self, kube: ReadOnlyKube) -> None:
        self.kube = kube

    async def run(self, args: CollectorArgs) -> list[Evidence]:
        if not args.namespace:
            return []
        selector = f"involvedObject.name={args.pod}" if args.pod else None
        events = await self.kube.list_events(args.namespace, selector)
        events.sort(key=lambda item: item.get("last_timestamp") or item.get("event_time") or "")
        recent = events[-20:]
        summary = "; ".join(
            f"{event.get('reason', 'Unknown')}: {event.get('message', '')}" for event in recent
        ) or "no matching Kubernetes events"
        return [_evidence(args, self.name, f"events/{args.namespace}/{args.pod or 'namespace'}", summary, recent)]


class PodLogsTool:
    name = "kubernetes.logs"
    description = "Read bounded current and previous pod logs."
    args_schema = CollectorArgs

    def __init__(self, kube: ReadOnlyKube) -> None:
        self.kube = kube

    async def run(self, args: CollectorArgs) -> list[Evidence]:
        if not args.namespace or not args.pod:
            return []
        current = await self.kube.read_pod_log(args.namespace, args.pod, container=args.container, tail_lines=200)
        previous = await self.kube.read_pod_log(
            args.namespace, args.pod, container=args.container, previous=True, tail_lines=200
        )
        combined = {"current": current, "previous": previous}
        summary = f"logs for {args.pod}: current_lines={len(current.splitlines())}, previous_lines={len(previous.splitlines())}"
        return [_evidence(args, self.name, f"logs/{args.namespace}/{args.pod}", summary, combined)]


class WorkloadRolloutTool:
    name = "kubernetes.rollout_history"
    description = "Read deployment template, ReplicaSet revisions, images, env keys, resources, and probes."
    args_schema = CollectorArgs

    def __init__(self, kube: ReadOnlyKube) -> None:
        self.kube = kube

    async def run(self, args: CollectorArgs) -> list[Evidence]:
        if not args.namespace or not args.workload:
            return []
        deployment = await self.kube.read_deployment(args.namespace, args.workload)
        replicasets = await self.kube.list_replicasets(args.namespace, f"app={args.workload}")
        template = deployment.get("spec", {}).get("template", {})
        spec = template.get("spec", {})
        containers = spec.get("containers", [])
        description = []
        for container in containers:
            env = [item.get("name") for item in container.get("env", [])]
            description.append(
                f"{container.get('name')}: image={container.get('image')}; env_keys={','.join(item for item in env if item)}; resources={container.get('resources', {})}; probes={container.get('readiness_probe', {})}"
            )
        summary = f"deployment {args.workload} template: {' | '.join(description)}; replicasets={len(replicasets)}"
        return [_evidence(args, self.name, f"deployment/{args.namespace}/{args.workload}", summary, {"deployment": deployment, "replicasets": replicasets})]


class ServiceEndpointsTool:
    name = "kubernetes.endpoints"
    description = "Read Service selectors, endpoint readiness, and selector mismatch signals."
    args_schema = CollectorArgs

    def __init__(self, kube: ReadOnlyKube) -> None:
        self.kube = kube

    async def run(self, args: CollectorArgs) -> list[Evidence]:
        if not args.namespace:
            return []
        service_name = args.service or args.workload
        if not service_name:
            return []
        service = await self.kube.read_service(args.namespace, service_name)
        endpoints = await self.kube.read_endpoints(args.namespace, service_name)
        subsets = endpoints.get("subsets", []) or []
        ready = sum(len(item.get("addresses", [])) for item in subsets)
        not_ready = sum(len(item.get("not_ready_addresses", [])) for item in subsets)
        selector = service.get("spec", {}).get("selector", {})
        mismatch = ready == 0
        summary = f"service {service_name}: selector={selector}; ready_endpoints={ready}; not_ready_endpoints={not_ready}; selector_mismatch={mismatch}"
        return [_evidence(args, self.name, f"service/{args.namespace}/{service_name}", summary, {"service": service, "endpoints": endpoints})]


class NamespaceOverviewTool:
    name = "kubernetes.namespace_overview"
    description = "Read non-ready pods in the investigation namespace."
    args_schema = CollectorArgs

    def __init__(self, kube: ReadOnlyKube) -> None:
        self.kube = kube

    async def run(self, args: CollectorArgs) -> list[Evidence]:
        if not args.namespace:
            return []
        pods = await self.kube.list_pods(args.namespace)
        non_ready = [pod for pod in pods if pod.get("status", {}).get("phase") != "Running"]
        summary = f"namespace {args.namespace}: pods={len(pods)}, non_ready={len(non_ready)}, ready={_ready_pods(pods)}"
        return [_evidence(args, self.name, f"namespace/{args.namespace}", summary, non_ready)]


def default_kubernetes_tools(kube: ReadOnlyKube) -> list[Any]:
    return [
        PodStatusTool(kube),
        PodEventsTool(kube),
        PodLogsTool(kube),
        WorkloadRolloutTool(kube),
        ServiceEndpointsTool(kube),
        NamespaceOverviewTool(kube),
    ]


__all__ = ["default_kubernetes_tools"]
