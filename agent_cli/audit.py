"""Small audit sink for local executions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from agent_protocol import OperationClass, redact_secrets


@dataclass(frozen=True)
class AuditRecord:
    execution_id: str
    user_id: str
    session_id: str
    request_id: str
    tool: str
    action: str
    operation: OperationClass
    outcome: str
    started_at: float
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets({"execution_id": self.execution_id, "user_id": self.user_id, "session_id": self.session_id, "request_id": self.request_id, "tool": self.tool, "action": self.action, "operation": self.operation.value, "outcome": self.outcome, "started_at": self.started_at, "duration_ms": self.duration_ms, "details": self.details})


AuditSink = Callable[[AuditRecord], None]


def new_record(*, user_id: str, session_id: str, request_id: str, tool: str, action: str, operation: OperationClass, outcome: str, started_at: float, duration_ms: float, details: dict[str, Any] | None = None) -> AuditRecord:
    return AuditRecord(str(uuid4()), user_id, session_id, request_id, tool, action, operation, outcome, started_at, duration_ms, details or {})


__all__ = ["AuditRecord", "AuditSink", "new_record"]
