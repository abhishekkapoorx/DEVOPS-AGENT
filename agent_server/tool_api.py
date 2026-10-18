"""HTTP boundary for the independently deployable registered Tool Service."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from fastapi import APIRouter, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

from agent_core.tools import ToolExecutionContext
from agent_server.auth_sessions import AuthSessionService
from agent_server.api.security import require_authenticated_user
from agent_server.tool_service import ToolService
from agent_core.runs import IdempotencyConflict


class ToolPrincipal(BaseModel):
    user_id: str
    scopes: frozenset[str] = frozenset()


class ToolCallInput(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    call_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def arguments_are_bounded(self):
        if len(json.dumps(self.arguments, separators=(",", ":")).encode("utf-8")) > 64_000:
            raise ValueError("Tool arguments exceed the request size limit")
        return self


class ToolResultOutput(BaseModel):
    call_id: str
    name: str
    status: str
    output: dict[str, Any]
    error: str | None
    duration_ms: float


def create_tool_router(
    service: ToolService,
    resolve_principal: Callable[[str | None], ToolPrincipal],
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["tools"])

    @router.get("/tools")
    async def list_tools(authorization: str | None = Header(default=None)):
        principal = resolve_principal(authorization)
        return [
            {
                "name": item.name,
                "version": item.version,
                "description": item.description,
                "input_schema": item.input_model.model_json_schema(),
                "output_schema": item.output_model.model_json_schema(),
                "required_scopes": sorted(item.required_scopes),
                "risk_class": item.risk_class,
                "execution_mode": item.execution_mode,
                "timeout_seconds": item.timeout_seconds,
                "requires_approval": item.requires_approval,
            }
            for item in service.list_tools(principal.scopes)
        ]

    @router.post("/tool-calls", response_model=ToolResultOutput)
    async def execute_tool(
        body: ToolCallInput,
        authorization: str | None = Header(default=None),
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
        correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
        traceparent: str | None = Header(default=None),
    ) -> ToolResultOutput:
        principal = resolve_principal(authorization)
        try:
            result = await service.execute(
                name=body.name,
                version=body.version,
                arguments=body.arguments,
                context=ToolExecutionContext(
                    user_id=principal.user_id,
                    run_id=body.run_id,
                    call_id=body.call_id,
                    scopes=principal.scopes,
                    correlation_id=correlation_id or body.run_id,
                    idempotency_key=idempotency_key,
                    traceparent=traceparent,
                ),
            )
        except IdempotencyConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return ToolResultOutput(**result.__dict__)

    return router


def create_tool_service_app(
    *, service: ToolService, auth_service: AuthSessionService,
    scopes_for_user: Callable[[str], frozenset[str]] | None = None,
) -> FastAPI:
    """Build a standalone Tool Service app with verified user identity."""

    def resolve_principal(authorization: str | None) -> ToolPrincipal:
        user = require_authenticated_user(authorization, auth_service)
        scopes = scopes_for_user(user.user_id) if scopes_for_user else user.scopes
        return ToolPrincipal(user_id=user.user_id, scopes=scopes)

    app = FastAPI(title="DevOps Tool Service", version="1")
    app.include_router(create_tool_router(service, resolve_principal))
    return app


__all__ = ["ToolPrincipal", "create_tool_router", "create_tool_service_app"]
