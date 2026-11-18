"""Stable alert identity used by deduplication."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from agent_server.alertmanager import NormalizedAlert


def alert_fingerprint(
    alert: NormalizedAlert,
    extra_label_names: Iterable[str] = (),
) -> str:
    """Hash only stable resource identity, never pod, severity, or timestamps."""

    labels = {
        name: alert.labels.get(name, "")
        for name in sorted(set(extra_label_names))
    }
    canonical = {
        "source": alert.source,
        "alertname": alert.alertname,
        "namespace": alert.namespace or "",
        "workload": alert.workload or "",
        "extra_labels": labels,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def delivery_key(alert: NormalizedAlert) -> str:
    """Return an idempotency key for one exact Alertmanager delivery."""

    encoded = json.dumps(
        {"source": alert.source, "owner_user_id": alert.owner_user_id, "alert": alert.raw},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["alert_fingerprint", "delivery_key"]
