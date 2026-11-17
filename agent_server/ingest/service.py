"""The future deduplication and investigation handoff boundary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Any

from agent_server.alertmanager import NormalizedAlert


logger = logging.getLogger(__name__)


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


async def ingest_alerts(session: Any, alerts: list[NormalizedAlert]) -> list[IngestResult]:
    """Placeholder for the next task's deduplication and investigation work."""

    for alert in alerts:
        logger.info(
            "accepted alert for ingestion",
            extra={"alert_fingerprint": alert.source_fingerprint, "alertname": alert.alertname},
        )
    return [
        IngestResult(
            alert_id=alert.source_fingerprint or alert.alertname,
            investigation_id=None,
            action="ignored",
        )
        for alert in alerts
    ]


__all__ = ["IngestResult", "ingest_alerts"]
