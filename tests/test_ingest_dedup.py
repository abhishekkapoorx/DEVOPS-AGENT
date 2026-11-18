import hashlib
import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_server.alertmanager import AlertNormalizationContext, normalize_alert
from agent_server.ingest.fingerprint import alert_fingerprint, delivery_key
from agent_server.ingest.service import ingest_alerts
from agent_server.persistence.postgres import (
    AlertRow,
    AuditLogRow,
    Base,
    InvestigationEvidenceRow,
    InvestigationRow,
)


def _normalized(status="firing", *, pod="checkoutservice-7d9f8b6c5d-x2kqp"):
    return normalize_alert(
        {
            "status": status,
            "labels": {
                "alertname": "KubePodCrashLooping",
                "namespace": "boutique",
                "deployment": "checkoutservice",
                "pod": pod,
                "severity": "critical",
            },
            "annotations": {"summary": "summary", "description": "description"},
            "startsAt": "2026-11-15T09:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z"
            if status == "firing"
            else "2026-11-15T09:05:00Z",
            "generatorURL": "http://prometheus.local",
            "fingerprint": "source-fingerprint",
        },
        AlertNormalizationContext({}, {}, datetime(2026, 11, 15, tzinfo=timezone.utc)),
    )


def test_alert_fingerprint_excludes_pod_severity_and_delivery_time():
    first = _normalized(pod="checkoutservice-aaaaaaa111-bbbbb")
    second = _normalized(pod="checkoutservice-ccccccc222-ddddd")

    assert alert_fingerprint(first) == alert_fingerprint(second)
    assert alert_fingerprint(first) == hashlib.sha256(
        json.dumps(
            {
                "source": "alertmanager",
                "alertname": "KubePodCrashLooping",
                "namespace": "boutique",
                "workload": "checkoutservice",
                "extra_labels": {},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def test_delivery_key_changes_for_resolution_but_not_repeated_exact_delivery():
    firing = _normalized()
    resolved = _normalized("resolved")

    assert delivery_key(firing) == delivery_key(firing)
    assert delivery_key(firing) != delivery_key(resolved)


def test_investigation_schema_contains_durable_queue_and_audit_tables():
    assert {"alerts", "investigations", "audit_log", "investigation_evidence"} <= set(
        Base.metadata.tables
    )
    assert "delivery_key" in AlertRow.__table__.columns
    assert "run_after" in InvestigationRow.__table__.columns
    assert "details" in AuditLogRow.__table__.columns
    assert "content_hash" in InvestigationEvidenceRow.__table__.columns


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="set TEST_DATABASE_URL to run real PostgreSQL ingestion/concurrency tests",
)
async def test_postgres_ingestion_creates_then_deduplicates_then_resolves():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        firing = _normalized()
        resolved = _normalized("resolved")
        async with sessions() as session:
            first = await ingest_alerts(session, [firing])
            repeat = await ingest_alerts(session, [firing])
            close = await ingest_alerts(session, [resolved])

        assert first[0].action == "created"
        assert repeat[0].action == "deduped"
        assert close[0].action == "resolved"
        assert first[0].investigation_id == repeat[0].investigation_id == close[0].investigation_id
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()
