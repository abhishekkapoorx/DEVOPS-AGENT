"""Deterministic, redacted Slack briefing delivery."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from agent_server.investigations.evidence import ContextPack
from agent_server.investigations.redaction import redact_text


logger = logging.getLogger(__name__)
SLACK_LIMIT = 40_000


def build_deterministic_briefing(
    pack: ContextPack,
    *,
    occurrence_count: int = 1,
    status: str = "Deterministic context pack. No LLM analysis.",
    reason: str | None = None,
) -> str:
    lines = [
        f"*Incident investigation: {pack.alertname}*",
        f"Status: {status}",
        f"Workload: {pack.workload or 'unknown'} | Namespace: {pack.namespace or 'unknown'} | Severity: {pack.severity}",
        f"Summary: {pack.summary}",
        f"Occurrences: {occurrence_count}",
    ]
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append("")
    lines.append("*Evidence*")
    for item in pack.evidence:
        lines.append(f"[{item.id}] {item.source}: {item.summary}")
    if pack.collection_errors:
        lines.append("")
        lines.append("*Collection errors*")
        for error in pack.collection_errors:
            lines.append(f"- {error['tool']}: {error['error']}")
    lines.extend(
        [
            "",
            "READ-ONLY analysis. No actions were taken.",
        ]
    )
    return _limit_message(redact_text("\n".join(lines)))


def _limit_message(message: str, limit: int = SLACK_LIMIT) -> str:
    if len(message) <= limit:
        return message
    marker = "\n… [briefing truncated]"
    return message[: limit - len(marker)] + marker


class SlackDeliveryError(RuntimeError):
    pass


class SlackPoster:
    def __init__(
        self,
        webhook_url: str | None = None,
        *,
        client_factory: Callable[[], Any] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.webhook_url = webhook_url if webhook_url is not None else os.getenv("SLACK_WEBHOOK_URL")
        self.client_factory = client_factory
        self.sleep = sleep
        self.max_attempts = max_attempts

    async def post(
        self,
        pack: ContextPack,
        *,
        occurrence_count: int = 1,
        status: str = "Deterministic context pack. No LLM analysis.",
        reason: str | None = None,
    ) -> bool:
        message = build_deterministic_briefing(
            pack,
            occurrence_count=occurrence_count,
            status=status,
            reason=reason,
        )
        if not self.webhook_url:
            logger.info("Slack webhook is unset; deterministic briefing:\n%s", message)
            return False

        client = self.client_factory() if self.client_factory else httpx.AsyncClient(timeout=10)
        owns_client = self.client_factory is None
        try:
            for attempt in range(self.max_attempts):
                response = await client.post(self.webhook_url, json={"text": message})
                if 200 <= response.status_code < 300:
                    return True
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise SlackDeliveryError(f"Slack rejected briefing with HTTP {response.status_code}")
                if attempt + 1 == self.max_attempts:
                    break
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                await self.sleep(delay)
            raise SlackDeliveryError("Slack delivery exhausted retries")
        finally:
            if owns_client:
                await client.aclose()


__all__ = ["SLACK_LIMIT", "SlackDeliveryError", "SlackPoster", "build_deterministic_briefing"]
