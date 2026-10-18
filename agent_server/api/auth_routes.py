"""HTTP contract for browser-assisted CLI authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from agent_server.auth_sessions import AuthError, AuthSessionService, DeviceMode, DeviceRateLimited
from .security import require_authenticated_user


class DeviceStartRequest(BaseModel):
    mode: DeviceMode


class DevicePollRequest(BaseModel):
    device_code: str = Field(min_length=20, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


def create_auth_router(service: AuthSessionService) -> APIRouter:
    """Create auth endpoints with session issuance delegated to an injected service."""
    router = APIRouter(prefix="/v1/auth", tags=["authentication"])

    @router.post("/device")
    async def start_device(body: DeviceStartRequest):
        return (await service.start_device(body.mode)).model_dump(mode="json")

    @router.post("/device/poll")
    async def poll_device(body: DevicePollRequest):
        try:
            result = await service.poll_device(body.device_code)
        except DeviceRateLimited as error:
            raise HTTPException(status_code=429, detail=str(error), headers={"Retry-After": str(service.poll_interval)}) from error
        except AuthError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        return result.model_dump(mode="json")

    @router.post("/refresh")
    async def refresh(body: RefreshRequest):
        try:
            return (await service.refresh(body.refresh_token)).model_dump(mode="json")
        except AuthError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(body: RefreshRequest) -> Response:
        await service.logout(body.refresh_token)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/me")
    async def current_user(authorization: Annotated[str | None, Header()] = None):
        principal = require_authenticated_user(authorization, service)
        return {"user_id": principal.user_id}

    return router


__all__ = ["create_auth_router"]
