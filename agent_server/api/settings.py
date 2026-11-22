"""Authenticated browser and JSON interfaces for integrations and reports."""

from __future__ import annotations

from pathlib import Path
import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from agent_server.alertmanager_manifests import helm_values, kustomize_bundle, operator_manifest
from agent_server.auth_sessions import AuthSessionService, AuthenticatedUser
from agent_server.integrations import (
    SLACK_PROVIDER,
    IntegrationValidationError,
    validate_slack_webhook_url,
)
from agent_server.investigations.slack import SlackDeliveryError, SlackPoster, build_test_briefing
from agent_server.persistence.postgres import (
    AlertRow,
    InvestigationEvidenceRow,
    InvestigationRow,
)
from agent_server.persistence.secrets import SecretRepository, mask_secret
from agent_server.web_templates import create_site_templates


def _alertmanager_config(secret: str, endpoint: str = "${DEVOPS_AGENT_PUBLIC_BASE_URL}/webhook/alertmanager") -> str:
    return (
        "receivers:\n"
        "  - name: incident-investigation-webhook\n"
        "    webhook_configs:\n"
        f"      - url: {endpoint}\n"
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


class SlackIntegrationInput(BaseModel):
    display_name: str = Field(default="Slack", min_length=1, max_length=128)
    webhook_url: str = Field(min_length=1, max_length=2048)
    enabled: bool = True


def create_settings_router(
    *,
    sessions: Any,
    secret_repository: SecretRepository | None,
    auth_service: AuthSessionService,
    template_dir: Path,
) -> APIRouter:
    router = APIRouter()
    templates = create_site_templates(template_dir, auth_service)
    manifest_artifacts: dict[str, tuple[str, str, str]] = {}

    def webhook_endpoint(request: Request) -> str:
        base_url = os.getenv("DEVOPS_AGENT_PUBLIC_BASE_URL", str(request.base_url).rstrip("/"))
        return base_url.rstrip("/") + "/webhook/alertmanager"

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

    def browser_user(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedUser:
        try:
            return current_user(request, authorization)
        except HTTPException as error:
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": "/login"},
                detail="Redirecting to sign in",
            ) from error

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

    async def integration_data(user_id: str) -> list[dict[str, Any]]:
        store = require_secret_store()
        rows = await store.list_integrations(user_id)
        result: list[dict[str, Any]] = []
        for row in rows:
            webhook_url = await store.decrypt_integration_webhook_url(row)
            result.append(
                {
                    "id": row.id,
                    "provider": row.provider,
                    "display_name": row.display_name,
                    "enabled": row.enabled,
                    "webhook_url_masked": mask_secret(webhook_url),
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
            )
        return result

    async def render_integrations(
        request: Request,
        user_id: str,
        *,
        message: str | None = None,
        status_code: int = 200,
    ):
        store = require_secret_store()
        slack = await store.get_integration(user_id, SLACK_PROVIDER)
        slack_webhook_url = (
            mask_secret(await store.decrypt_integration_webhook_url(slack)) if slack else None
        )
        return templates.TemplateResponse(
            request=request,
            name="integrations.html",
            context={
                "title": "Integrations",
                "integrations": await integration_data(user_id),
                "slack": slack,
                "slack_webhook_url": slack_webhook_url,
                "message": message,
            },
            status_code=status_code,
        )

    def require_slack_provider(provider: str) -> None:
        if provider != SLACK_PROVIDER:
            raise HTTPException(status_code=404, detail="Integration not found")

    @router.get("/settings", include_in_schema=False)
    async def settings_page(request: Request, user: AuthenticatedUser = Depends(browser_user)):
        store = require_secret_store()
        webhooks = await store.list_webhook_secrets(user.user_id)
        resources = await store.list_resource_secrets(user.user_id)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "title": "Secrets and webhooks",
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
        user: AuthenticatedUser = Depends(browser_user),
    ):
        store = require_secret_store()
        _, raw_secret = await store.create_webhook_secret(user.user_id, name.strip())
        artifact_id = secrets.token_urlsafe(24)
        endpoint = webhook_endpoint(request)
        manifest_artifacts[artifact_id] = (user.user_id, endpoint, raw_secret)
        webhooks = await store.list_webhook_secrets(user.user_id)
        resources = await store.list_resource_secrets(user.user_id)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "title": "Secrets and webhooks",
                "webhooks": webhooks,
                "resources": resources,
                "mask_secret": mask_secret,
                "new_webhook_secret": raw_secret,
                "webhook_endpoint": endpoint,
                "alertmanager_config": _alertmanager_config(raw_secret, endpoint),
                "manifest_id": artifact_id,
            },
        )

    @router.get("/settings/webhook-manifests/{artifact_id}/{manifest_format}", include_in_schema=False)
    async def download_webhook_manifest(
        artifact_id: str,
        manifest_format: str,
        user: AuthenticatedUser = Depends(browser_user),
    ):
        artifact = manifest_artifacts.get(artifact_id)
        if artifact is None or artifact[0] != user.user_id:
            raise HTTPException(status_code=404, detail="Manifest not found or expired")
        _, endpoint, raw_secret = artifact
        if manifest_format == "kustomize":
            return Response(
                content=kustomize_bundle(endpoint, raw_secret),
                media_type="application/zip",
                headers={"Content-Disposition": 'attachment; filename="alertmanager-webhook-kustomize.zip"'},
            )
        if manifest_format == "helm":
            content, filename = helm_values(endpoint, raw_secret), "alertmanager-webhook-values.yaml"
        elif manifest_format == "operator":
            content, filename = operator_manifest(endpoint, raw_secret), "alertmanagerconfig.yaml"
        else:
            raise HTTPException(status_code=404, detail="Unknown manifest format")
        return Response(
            content=content,
            media_type="application/yaml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/settings/webhook-secrets/{secret_id}/revoke", include_in_schema=False)
    async def revoke_webhook_secret_page(secret_id: str, user: AuthenticatedUser = Depends(browser_user)):
        await require_secret_store().revoke_webhook_secret(user.user_id, secret_id)
        return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/settings/resource-secrets", include_in_schema=False)
    async def save_resource_secret_page(
        provider: str = Form(min_length=1, max_length=128),
        name: str = Form(min_length=1, max_length=128),
        value: str = Form(min_length=1, max_length=100_000),
        user: AuthenticatedUser = Depends(browser_user),
    ):
        await require_secret_store().save_resource_secret(user.user_id, provider, name, value)
        return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/settings/resource-secrets/{secret_id}/delete", include_in_schema=False)
    async def delete_resource_secret_page(secret_id: str, user: AuthenticatedUser = Depends(browser_user)):
        await require_secret_store().delete_resource_secret(user.user_id, secret_id)
        return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)

    @router.get("/settings/integrations", include_in_schema=False)
    async def integrations_page(request: Request, user: AuthenticatedUser = Depends(browser_user)):
        return await render_integrations(request, user.user_id)

    @router.post("/settings/integrations", include_in_schema=False)
    async def save_slack_integration(
        request: Request,
        display_name: str = Form(default="Slack", max_length=128),
        webhook_url: str = Form(default="", max_length=2048),
        enabled: bool = Form(default=False),
        user: AuthenticatedUser = Depends(browser_user),
    ):
        try:
            validated_url = validate_slack_webhook_url(webhook_url)
        except IntegrationValidationError as error:
            return await render_integrations(request, user.user_id, message=str(error), status_code=400)
        name = display_name.strip() or "Slack"
        await require_secret_store().save_integration(
            user.user_id, SLACK_PROVIDER, name, validated_url, enabled
        )
        return RedirectResponse("/settings/integrations", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/settings/integrations/{provider}/delete", include_in_schema=False)
    async def delete_integration_page(
        provider: str,
        user: AuthenticatedUser = Depends(browser_user),
    ):
        require_slack_provider(provider)
        await require_secret_store().delete_integration(user.user_id, provider)
        return RedirectResponse("/settings/integrations", status_code=status.HTTP_303_SEE_OTHER)

    @router.post("/settings/integrations/{provider}/test", include_in_schema=False)
    async def test_integration_page(
        request: Request,
        provider: str,
        user: AuthenticatedUser = Depends(browser_user),
    ):
        require_slack_provider(provider)
        store = require_secret_store()
        row = await store.get_integration(user.user_id, provider)
        if row is None or not row.enabled:
            return await render_integrations(
                request,
                user.user_id,
                message="Save and enable the Slack integration before sending a test message.",
                status_code=400,
            )
        webhook_url = await store.decrypt_integration_webhook_url(row)
        try:
            validate_slack_webhook_url(webhook_url)
            delivered = await SlackPoster(webhook_url).post_text(
                build_test_briefing(row.display_name)
            )
        except (IntegrationValidationError, SlackDeliveryError) as error:
            return await render_integrations(request, user.user_id, message=str(error), status_code=400)
        if not delivered:
            return await render_integrations(
                request,
                user.user_id,
                message="Slack did not accept the test message.",
                status_code=400,
            )
        return await render_integrations(
            request, user.user_id, message="Test message delivered to Slack."
        )

    @router.get("/v1/settings/integrations")
    async def list_integrations(user: AuthenticatedUser = Depends(current_user)):
        return await integration_data(user.user_id)

    @router.post("/v1/settings/integrations")
    async def save_integration(
        body: SlackIntegrationInput,
        user: AuthenticatedUser = Depends(current_user),
    ):
        try:
            validated_url = validate_slack_webhook_url(body.webhook_url)
        except IntegrationValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        row = await require_secret_store().save_integration(
            user.user_id,
            SLACK_PROVIDER,
            body.display_name.strip() or "Slack",
            validated_url,
            body.enabled,
        )
        webhook_url = await require_secret_store().decrypt_integration_webhook_url(row)
        return {
            "id": row.id,
            "provider": row.provider,
            "display_name": row.display_name,
            "enabled": row.enabled,
            "webhook_url_masked": mask_secret(webhook_url),
        }

    @router.delete("/v1/settings/integrations/{provider}")
    async def delete_integration(
        provider: str,
        user: AuthenticatedUser = Depends(current_user),
    ):
        require_slack_provider(provider)
        if not await require_secret_store().delete_integration(user.user_id, provider):
            raise HTTPException(status_code=404, detail="Integration not found")
        return {"deleted": True}

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
    async def investigations_page(request: Request, user: AuthenticatedUser = Depends(browser_user)):
        return templates.TemplateResponse(
            request=request,
            name="investigations.html",
            context={"title": "Investigations", "investigations": await report_data(user.user_id)},
        )

    @router.get("/investigations/{investigation_id}", include_in_schema=False)
    async def investigation_page(
        request: Request,
        investigation_id: str,
        user: AuthenticatedUser = Depends(browser_user),
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
