from datetime import datetime, timezone
import ast
from pathlib import Path

import pytest

from agent_server.alertmanager import AlertNormalizationContext, normalize_alert
from agent_server.investigations.context import build_context_pack
from agent_server.investigations.registry import CollectorArgs, ToolRegistry
from agent_server.investigations.redaction import redact_text
from agent_server.tools.collectors.kubernetes_tools import PodStatusTool


class FakeSession:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    async def execute(self, statement):
        self.rows.append(statement)


class FakeKube:
    async def read_pod(self, namespace, name):
        return {
            "metadata": {"name": name},
            "status": {
                "phase": "Running",
                "container_statuses": [{"restart_count": 1, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
                "conditions": [{"type": "Ready", "status": "False"}],
            },
        }

    async def list_pods(self, namespace, label_selector=None):
        return []


def _alert():
    return normalize_alert(
        {
            "status": "firing",
            "labels": {"alertname": "Test", "namespace": "boutique", "pod": "checkout-abc"},
            "annotations": {"summary": "test", "description": "test"},
            "startsAt": "2026-11-15T09:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
        },
        AlertNormalizationContext({}, {}, datetime.now(timezone.utc)),
    )


@pytest.mark.asyncio
async def test_registry_allowlist_and_pod_status_evidence():
    session = FakeSession()
    registry = ToolRegistry([PodStatusTool(FakeKube())], session)

    evidence = await registry.run(
        "kubernetes.pod_status",
        CollectorArgs(investigation_id="i", namespace="boutique", pod="checkout"),
    )

    assert evidence[0].source == "kubernetes.pod_status"
    assert "CrashLoopBackOff" in evidence[0].summary
    assert registry.call_count == 1
    assert session.rows


@pytest.mark.asyncio
async def test_context_pack_records_collector_failures_without_crashing():
    session = FakeSession()
    registry = ToolRegistry([PodStatusTool(FakeKube())], session, max_calls=1)

    pack = await build_context_pack(_alert(), "i", registry)

    assert pack.evidence
    assert len(pack.collection_errors) == 5
    assert pack.tool_call_count == 1


def test_redaction_covers_bearer_jwt_and_private_key():
    value = "Bearer abcdefghijklmnopqrstuvwxyz eyJheader.payload.signature -----BEGIN PRIVATE KEY-----secret-----END PRIVATE KEY-----"

    result = redact_text(value)

    assert "abcdefghijklmnopqrstuvwxyz" not in result
    assert "eyJheader" not in result
    assert "REDACTED_PRIVATE_KEY" in result
    assert "secret" not in result


def test_kubernetes_collectors_contain_no_write_operations():
    forbidden = {"exec", "connect", "scale"}
    violations = []
    for path in Path("agent_server/tools/collectors").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if name in forbidden or name.startswith(("create_", "patch_", "delete_", "replace_")):
                    violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []
