"""Public landing page and browser sign-in entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates


def create_website_router(template_dir: Path) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=template_dir)

    @router.get("/", include_in_schema=False)
    async def landing_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="landing.html",
            context={"title": "Trustworthy incident investigations"},
        )

    @router.get("/login", include_in_schema=False)
    async def login_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"title": "Sign in"},
        )

    return router


__all__ = ["create_website_router"]
