"""HTTP boundary for Alertmanager notifications."""

from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from pydantic import ValidationError

from agent_server.alertmanager import (
    AlertNormalizationContext,
    AlertmanagerWebhook,
    NormalizedAlert,
    normalize_alert,
)
from agent_server.ingest.service import IngestResult, ingest_alerts
from agent_server.persistence.postgres import RawWebhookRow


logger = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 1024 * 1024
SAFE_HEADERS = ("content-type", "user-agent", "x-forwarded-for", "x-request-id")
SessionFactory = Any
IngestAlerts = Callable[[Any, list[NormalizedAlert]], Awaitable[list[IngestResult]]]
WebhookSecretOwner = Callable[[str], Awaitable[str | None]]


def create_webhook_router(
    *,
    session_factory: SessionFactory | None,
    webhook_token: str | None,
    ingest_alerts_fn: IngestAlerts | None = None,
    webhook_secret_owner: WebhookSecretOwner | None = None,
) -> APIRouter:
    router = APIRouter()
    ingest = ingest_alerts_fn or ingest_alerts

    @router.post(
        "/webhook/alertmanager",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["webhooks"],
    )
    async def alertmanager_webhook(
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
    ) -> dict[str, int]:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        response.headers["X-Request-ID"] = request_id
        log_context = {"request_id": request_id, "webhook": "alertmanager"}
        owner_user_id = "system" if webhook_token is None and webhook_secret_owner is None else ""

        authorization = request.headers.get("Authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        if webhook_token is not None:
            valid = scheme.lower() == "bearer" and hmac.compare_digest(supplied, webhook_token)
            if valid:
                owner_user_id = "system"
            elif webhook_secret_owner is not None and scheme.lower() == "bearer":
                owner_user_id = await webhook_secret_owner(supplied) or ""
            if not valid and not owner_user_id:
                logger.warning("rejected webhook authentication", extra=log_context)
                raise HTTPException(status_code=401, detail="Invalid webhook credentials")
        elif webhook_secret_owner is not None:
            if scheme.lower() != "bearer":
                raise HTTPException(status_code=401, detail="Bearer webhook secret required")
            owner_user_id = await webhook_secret_owner(supplied) or ""
            if not owner_user_id:
                logger.warning("rejected webhook authentication", extra=log_context)
                raise HTTPException(status_code=401, detail="Invalid webhook credentials")

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = MAX_WEBHOOK_BYTES + 1
            if declared_length > MAX_WEBHOOK_BYTES:
                raise HTTPException(status_code=413, detail="Webhook body is too large")

        body_parts: list[bytes] = []
        body_size = 0
        async for chunk in request.stream():
            body_size += len(chunk)
            if body_size > MAX_WEBHOOK_BYTES:
                raise HTTPException(status_code=413, detail="Webhook body is too large")
            body_parts.append(chunk)
        body = b"".join(body_parts)

        try:
            decoded = json.loads(body)
            payload = AlertmanagerWebhook.model_validate(decoded)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail="Invalid Alertmanager webhook payload") from exc

        if payload.version != "4":
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported Alertmanager webhook version: {payload.version}; expected 4",
            )
        if session_factory is None:
            raise HTTPException(status_code=503, detail="Webhook persistence is unavailable")

        received_at = datetime.now(timezone.utc)
        headers = {name: request.headers.get(name) for name in SAFE_HEADERS if request.headers.get(name)}
        normalized: list[NormalizedAlert] = []
        skipped = 0
        context = AlertNormalizationContext(
            common_labels={**payload.group_labels, **payload.common_labels},
            common_annotations=payload.common_annotations,
            received_at=received_at,
        )
        async with session_factory() as session:
            session.add(
                RawWebhookRow(
                    owner_user_id=owner_user_id,
                    received_at=received_at,
                    headers=headers,
                    body=decoded,
                )
            )
            await session.commit()

            for raw_alert in payload.alerts:
                try:
                    normalized.append(
                        normalize_alert(raw_alert, context).model_copy(
                            update={"owner_user_id": owner_user_id}
                        )
                    )
                except ValidationError as exc:
                    skipped += 1
                    logger.warning(
                        "skipped malformed alert",
                        extra={**log_context, "validation_error": str(exc.errors()[0]["type"])},
                    )


        async def handoff() -> None:
            try:
                async with session_factory() as ingest_session:
                    await ingest(ingest_session, normalized)
            except Exception:
                logger.exception("Alertmanager ingestion handoff failed", extra=log_context)

        background_tasks.add_task(handoff)

        logger.info(
            "processed Alertmanager webhook",
            extra={
                **log_context,
                "received": len(payload.alerts),
                "accepted": len(normalized),
                "skipped": skipped,
            },
        )
        return {"received": len(payload.alerts), "accepted": len(normalized), "skipped": skipped}

    return router


__all__ = ["MAX_WEBHOOK_BYTES", "create_webhook_router"]
