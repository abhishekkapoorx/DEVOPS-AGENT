"""Bounded, audited collector registry."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agent_server.investigations.evidence import Evidence
from agent_server.investigations.redaction import canonical_redacted_json, redact
from agent_server.persistence.postgres import AuditLogRow, InvestigationEvidenceRow


class Tool(Protocol):
    name: str
    description: str
    args_schema: type[BaseModel]

    async def run(self, args: BaseModel) -> list[Evidence]: ...


class CollectorArgs(BaseModel):
    investigation_id: str
    namespace: str | None = None
    workload: str | None = None
    pod: str | None = None
    container: str | None = None
    service: str | None = None


class ToolRegistry:
    def __init__(
        self,
        tools: list[Tool],
        session: Any,
        *,
        max_calls: int = 25,
        timeout_seconds: float = 10,
        max_output_bytes: int = 32_000,
    ) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._session = session
        self.max_calls = max_calls
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.call_count = 0

    async def run(self, name: str, args: BaseModel | dict[str, Any]) -> list[Evidence]:
        if name not in self._tools:
            raise ValueError(f"collector is not allowlisted: {name}")
        if self.call_count >= self.max_calls:
            raise RuntimeError("maximum collector calls exceeded")
        tool = self._tools[name]
        parsed = args if isinstance(args, tool.args_schema) else tool.args_schema.model_validate(args)
        self.call_count += 1
        started = datetime.now(timezone.utc)
        try:
            evidence = await asyncio.wait_for(tool.run(parsed), timeout=self.timeout_seconds)
            output = []
            for item in evidence:
                redacted = redact(item.raw)
                serialized = canonical_redacted_json(redacted).encode()
                truncated = item.truncated
                if len(serialized) > self.max_output_bytes:
                    serialized = serialized[: self.max_output_bytes]
                    redacted = {"preview": serialized.decode(errors="replace"), "truncated": True}
                    truncated = True
                item.raw = redacted
                item.truncated = truncated
                item.content_hash = hashlib.sha256(serialized).hexdigest()
                await self._session.execute(
                    pg_insert(InvestigationEvidenceRow)
                    .values(
                        id=item.id,
                        investigation_id=item.investigation_id,
                        source=item.source,
                        query=item.query,
                        query_hash=hashlib.sha256(item.query.encode()).hexdigest(),
                        fetched_at=item.fetched_at,
                        summary=item.summary,
                        raw_ref=item.raw_ref,
                        raw=item.raw,
                        truncated=item.truncated,
                        content_hash=item.content_hash,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["investigation_id", "source", "query_hash"]
                    )
                )
                output.append(item)
            self._session.add(
                AuditLogRow(
                    ts=datetime.now(timezone.utc),
                    actor="investigation-worker",
                    action="collector_completed",
                    object_type="investigation",
                    object_id=parsed.investigation_id,
                    details={"tool": name, "duration_ms": (datetime.now(timezone.utc) - started).total_seconds() * 1000},
                )
            )
            return output
        except Exception as exc:
            self._session.add(
                AuditLogRow(
                    ts=datetime.now(timezone.utc),
                    actor="investigation-worker",
                    action="collector_failed",
                    object_type="investigation",
                    object_id=parsed.investigation_id,
                    details={"tool": name, "error": type(exc).__name__},
                )
            )
            raise


__all__ = ["CollectorArgs", "Tool", "ToolRegistry"]
