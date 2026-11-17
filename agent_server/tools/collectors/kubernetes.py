"""Official Kubernetes client adapter exposing read-only operations only."""

from __future__ import annotations

from typing import Any


class ReadOnlyKube:
    """Small adapter containing only Kubernetes get/list/read operations."""

    def __init__(self, core: Any, apps: Any) -> None:
        self.core = core
        self.apps = apps

    @classmethod
    async def from_environment(cls) -> "ReadOnlyKube":
        from kubernetes_asyncio import client, config
        from kubernetes_asyncio.config.config_exception import ConfigException

        try:
            await config.load_incluster_config()
        except ConfigException:
            await config.load_kube_config()
        return cls(client.CoreV1Api(), client.AppsV1Api())

    async def read_pod(self, namespace: str, name: str) -> dict[str, Any]:
        return (await self.core.read_namespaced_pod(name=name, namespace=namespace)).to_dict()

    async def list_pods(self, namespace: str, label_selector: str | None = None) -> list[dict[str, Any]]:
        result = await self.core.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        return [item.to_dict() for item in result.items]

    async def list_events(self, namespace: str, field_selector: str | None = None) -> list[dict[str, Any]]:
        result = await self.core.list_namespaced_event(namespace=namespace, field_selector=field_selector)
        return [item.to_dict() for item in result.items]

    async def read_pod_log(
        self, namespace: str, name: str, *, container: str | None = None, previous: bool = False, tail_lines: int = 200
    ) -> str:
        return await self.core.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            container=container,
            previous=previous,
            tail_lines=tail_lines,
        )

    async def read_deployment(self, namespace: str, name: str) -> dict[str, Any]:
        return (await self.apps.read_namespaced_deployment(name=name, namespace=namespace)).to_dict()

    async def list_replicasets(self, namespace: str, label_selector: str | None = None) -> list[dict[str, Any]]:
        result = await self.apps.list_namespaced_replica_set(namespace=namespace, label_selector=label_selector)
        return [item.to_dict() for item in result.items]

    async def read_service(self, namespace: str, name: str) -> dict[str, Any]:
        return (await self.core.read_namespaced_service(name=name, namespace=namespace)).to_dict()

    async def read_endpoints(self, namespace: str, name: str) -> dict[str, Any]:
        return (await self.core.read_namespaced_endpoints(name=name, namespace=namespace)).to_dict()


__all__ = ["ReadOnlyKube"]
