"""Shared server-rendered website templates and navigation context."""

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from agent_server.auth_sessions import AuthSessionService


def create_site_templates(
    template_dir: Path,
    auth_service: AuthSessionService | None = None,
) -> Jinja2Templates:
    def navigation_context(request: Request) -> dict[str, bool]:
        token = request.cookies.get("devops_access_token", "")
        return {
            "authenticated": bool(auth_service and auth_service.current_user(token)),
        }

    return Jinja2Templates(directory=template_dir, context_processors=[navigation_context])


__all__ = ["create_site_templates"]
