"""Shared verified bearer-token handling for REST routes."""

from __future__ import annotations

from fastapi import HTTPException

from agent_server.auth_sessions import AuthSessionService, AuthenticatedUser


def require_authenticated_user(
    authorization: str | None, auth_service: AuthSessionService
) -> AuthenticatedUser:
    """Resolve identity exclusively from a verified access-token claim."""
    scheme, separator, token = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer access token required")
    user = auth_service.current_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    return user


__all__ = ["require_authenticated_user"]
