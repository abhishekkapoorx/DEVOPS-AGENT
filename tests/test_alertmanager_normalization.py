from datetime import datetime, timezone

import pytest

from agent_server.alertmanager import AlertNormalizationContext, normalize_alert


def _context(**kwargs):
    return AlertNormalizationContext(
        common_labels=kwargs.get("common_labels", {}),
        common_annotations=kwargs.get("common_annotations", {}),
        received_at=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
    )


def _alert(**kwargs):
    value = {
        "status": "firing",
        "labels": {
            "alertname": "KubePodCrashLooping",
            "namespace": "boutique",
            "pod": "checkoutservice-7d9f8b6c5d-x2kqp",
            "severity": "critical",
        },
        "annotations": {"summary": "crash", "description": "restarting"},
        "startsAt": "2026-11-15T09:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "http://prometheus.local/graph",
        "fingerprint": "abc123",
    }
    value.update(kwargs)
    return value


def test_normalize_alert_strips_pod_hash_and_preserves_context():
    normalized = normalize_alert(_alert(), _context())

    assert normalized.workload == "checkoutservice"
    assert normalized.pod == "checkoutservice-7d9f8b6c5d-x2kqp"
    assert normalized.source == "alertmanager"
    assert normalized.source_fingerprint == "abc123"
    assert normalized.ended_at is None
    assert normalized.received_at.isoformat() == "2026-11-15T10:00:00+00:00"


def test_normalize_alert_strips_replica_set_hash_from_workload_label():
    normalized = normalize_alert(
        _alert(labels={"alertname": "Test", "deployment": "checkoutservice-7d9f8b6c5d"}),
        _context(),
    )

    assert normalized.workload == "checkoutservice"


@pytest.mark.parametrize(
    ("status", "expected"),
    [("firing", "firing"), ("resolved", "resolved")],
)
def test_normalize_alert_preserves_lifecycle_status(status, expected):
    normalized = normalize_alert(_alert(status=status), _context())

    assert normalized.status == expected


def test_normalize_alert_uses_common_values_and_alertname_fallbacks():
    normalized = normalize_alert(
        {
            "status": "firing",
            "labels": {},
            "annotations": {},
            "startsAt": "2026-11-15T09:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "",
        },
        _context(
            common_labels={"alertname": "MissingLabels", "namespace": "default"},
        ),
    )

    assert normalized.alertname == "MissingLabels"
    assert normalized.severity == "unknown"
    assert normalized.namespace == "default"
    assert normalized.summary == "MissingLabels"
    assert normalized.description == "MissingLabels"
    assert normalized.labels == {}
    assert normalized.annotations == {}
