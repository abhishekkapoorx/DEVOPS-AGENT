"""Evidence and deterministic context-pack models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:12]}")
    investigation_id: str
    source: str
    query: str
    fetched_at: datetime
    summary: str
    raw_ref: str
    truncated: bool = False
    raw: Any = None
    content_hash: str = ""


class ContextPack(BaseModel):
    investigation_id: str
    alertname: str
    namespace: str | None
    workload: str | None
    severity: str
    summary: str
    evidence: list[Evidence] = Field(default_factory=list)
    collection_errors: list[dict[str, str]] = Field(default_factory=list)
    tool_call_count: int = 0


__all__ = ["ContextPack", "Evidence"]
