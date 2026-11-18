"""Authenticated browser and JSON interfaces for integrations and reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select

from agent_server.auth_sessions import AuthSessionService, AuthenticatedUser
from agent_server.persistence.postgres import (
    AlertRow,
    InvestigationEvidenceRow,
    InvestigationRow,
)
from agent_server.persistence.secrets import SecretRepository, mask_secret


def _alertmanager_config(secret: str) -> str:
    return (
        "receivers:\n"
        "  - name: incident-investigation-webhook\n"
        "    webhook_configs:\n"
        "      - url: ${DEVOPS_AGENT_PUBLIC_BASE_URL}/webhook/alertmanager\n"
        "        send_resolved: true\n"
        "        http_config:\n"
        "          authorization:\n"
        "            type: Bearer\n"
        f"            credentials: {secret}\n"
    )


class ResourceSecretInput(BaseModel):
    provider: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=100_000)


def create_settings_router(
    *,
    sessions: Any,
    secret_repository: SecretRepository | None,
    auth_service: AuthSessionService,
    template_dir: Path,
) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=template_dir)

    def current_user(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedUser:
        token = request.cookies.get("devops_access_token")
        if not token and authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer":
                token = None
        user = auth_service.current_user(token or "")
        if user is None:
            raise HTTPException(status_code=401, detail="Website sign-in required")
        return user

    def require_secret_store() -> SecretRepository:
        if secret_repository is None:
            raise HTTPException(
                status_code=503,
                detail="Secret storage is not configured; set ENCRYPTION_KEY and restart the API",
            )
        return secret_repository

    async def report_data(user_id: str) -> list[dict[str, Any]]:
        async with sessions() as session:
            rows = (
                await session.scalars(
                    select(InvestigationRow)
                    .where(InvestigationRow.owner_user_id == user_id)
                    .order_by(InvestigationRow.updated_at.desc())
                )
            ).all()
        return [
            {
                "id": row.id,
                "alertname": row.alertname,
                "status": row.status,
                "namespace": row.namespace,
                "workload": row.workload,
                "severity": row.severity,
                "occurrence_count": row.occurrence_count,
                "first_seen_at": row.first_seen_at.isoformat(),
                "last_seen_at": row.last_seen_at.isoformat(),
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                "result": row.result or {},
                "verifier_report": row.verifier_report or {},
            }
            for row in rows
        ]

    @router.get("/settings", include_in_schema=False)
    async def settings_page(request: Request, user: AuthenticatedUser = Depends(current_user)):
        store = require_secret_store()
        webhooks = await store.list_webhook_secrets(user.user_id)
        resources = await store.list_resource_secrets(user.user_id)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "title": "Integrations",
                "webhooks": webhooks,
                "resources": resources,
                "mask_secret": mask_secret,
                "new_webhook_secret": None,
            },
        )

    @router.post("/settings/webhook-secrets", include_in_schema=False)
    async def create_webhook_secret_page(
        request: Request,
        name: str = Form(min_length=1, max_length=128),
        user: AuthenticatedUser = Depends(current_user),
    ):
        store = require_secret_store()
        _, raw_secret = await store.create_webhook_secret(user.user_id, name.strip())
        webhooks = await store.list_webhook_secrets(user.user_id)
        resources = await store.list_resource_secrets(user.user_id)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "title": "Integrations",
                "webhooks": webhooks,
                "resources": resources,
                "mask_secret": mask_secret,
                "new_webhook_secret": raw_secret,
                "alertmanager_config": _alertmanager_config(raw_secret),
            },
        )

    @router.post("/settings/webhook-secrets/{secret_id}/revoke", include_in_schema=False)
    async def revoke_webhook_secret_page(secret_id: str, user: AuthenticatedUser = Depends(current_user)):
        await require_secret_store().revoke_webhook_secret(user.user_id, secret_id)
        return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/settings/resource-secrets", include_in_schema=False)
    async def save_resource_secret_page(
        provider: str = Form(min_length=1, max_length=128),
        name: str = Form(min_length=1, max_length=128),
        value: str = Form(min_length=1, max_length=100_000),
        user: AuthenticatedUser = Depends(current_user),
    ):
        await require_secret_store().save_resource_secret(user.user_id, provider, name, value)
        return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/settings/resource-secrets/{secret_id}/delete", include_in_schema=False)
    async def delete_resource_secret_page(secret_id: str, user: AuthenticatedUser = Depends(current_user)):
        await require_secret_store().delete_resource_secret(user.user_id, secret_id)
        return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)

    @router.get("/v1/settings/webhook-secrets")
    async def list_webhook_secrets(user: AuthenticatedUser = Depends(current_user)):
        rows = await require_secret_store().list_webhook_secrets(user.user_id)
        return [{"id": row.id, "name": row.name, "created_at": row.created_at, "last_used_at": row.last_used_at} for row in rows]

    @router.post("/v1/settings/webhook-secrets")
    async def create_webhook_secret(body: dict[str, str], user: AuthenticatedUser = Depends(current_user)):
        name = body.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")
        row, raw_secret = await require_secret_store().create_webhook_secret(user.user_id, name)
        return {
            "id": row.id,
            "name": row.name,
            "secret": raw_secret,
            "webhook_url": "/webhook/alertmanager",
            "alertmanager_config": _alertmanager_config(raw_secret),
        }

    @router.get("/v1/settings/resource-secrets")
    async def list_resource_secrets(user: AuthenticatedUser = Depends(current_user)):
        rows = await require_secret_store().list_resource_secrets(user.user_id)
        return [{"id": row.id, "provider": row.provider, "name": row.name, "updated_at": row.updated_at} for row in rows]

    @router.post("/v1/settings/resource-secrets")
    async def save_resource_secret(body: ResourceSecretInput, user: AuthenticatedUser = Depends(current_user)):
        row = await require_secret_store().save_resource_secret(user.user_id, body.provider, body.name, body.value)
        return {"id": row.id, "provider": row.provider, "name": row.name, "masked": mask_secret(body.value)}

    @router.get("/investigations", include_in_schema=False)
    async def investigations_page(request: Request, user: AuthenticatedUser = Depends(current_user)):
        return templates.TemplateResponse(
            request=request,
            name="investigations.html",
            context={"title": "Investigations", "investigations": await report_data(user.user_id)},
        )

    @router.get("/investigations/{investigation_id}", include_in_schema=False)
    async def investigation_page(
        request: Request,
        investigation_id: str,
        user: AuthenticatedUser = Depends(current_user),
    ):
        report = await get_report(investigation_id, user.user_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return templates.TemplateResponse(request=request, name="investigation.html", context={"title": "Investigation report", "report": report})

    @router.get("/v1/investigations")
    async def list_investigations(user: AuthenticatedUser = Depends(current_user)):
        return await report_data(user.user_id)

    async def get_report(investigation_id: str, user_id: str) -> dict[str, Any] | None:
        async with sessions() as session:
            investigation = await session.scalar(
                select(InvestigationRow).where(
                    InvestigationRow.id == investigation_id,
                    InvestigationRow.owner_user_id == user_id,
                )
            )
            if investigation is None:
                return None
            alerts = (
                await session.scalars(
                    select(AlertRow).where(AlertRow.investigation_id == investigation_id).order_by(AlertRow.received_at)
                )
            ).all()
            evidence = (
                await session.scalars(
                    select(InvestigationEvidenceRow)
                    .where(InvestigationEvidenceRow.investigation_id == investigation_id)
                    .order_by(InvestigationEvidenceRow.fetched_at)
                )
            ).all()
        return {
            "id": investigation.id,
            "alertname": investigation.alertname,
            "status": investigation.status,
            "namespace": investigation.namespace,
            "workload": investigation.workload,
            "severity": investigation.severity,
            "occurrence_count": investigation.occurrence_count,
            "first_seen_at": investigation.first_seen_at,
            "last_seen_at": investigation.last_seen_at,
            "resolved_at": investigation.resolved_at,
            "result": investigation.result or {},
            "verifier_report": investigation.verifier_report or {},
            "alerts": [{"status": item.status, "summary": item.summary, "received_at": item.received_at} for item in alerts],
            "evidence": [{"id": item.id, "source": item.source, "summary": item.summary, "query": item.query, "truncated": item.truncated} for item in evidence],
        }

    @router.get("/v1/investigations/{investigation_id}")
    async def investigation_json(investigation_id: str, user: AuthenticatedUser = Depends(current_user)):
        report = await get_report(investigation_id, user.user_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return report

    return router


__all__ = ["create_settings_router"]
