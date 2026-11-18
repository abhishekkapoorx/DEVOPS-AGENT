"""Public landing page and browser sign-in entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.templating import Jinja2Templates

from agent_server.accounts import AccountError, LocalAccountService
from agent_server.auth_sessions import AuthSessionService
from fastapi.responses import RedirectResponse


def create_website_router(
    template_dir: Path,
    *,
    accounts: LocalAccountService | None = None,
    auth_service: AuthSessionService | None = None,
) -> APIRouter:
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
    async def login_page(request: Request, mode: str = "signin"):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"title": "Sign in", "mode": mode if mode in {"signin", "signup"} else "signin", "message": None},
        )

    async def browser_tokens(user_id: str) -> RedirectResponse:
        if auth_service is None:
            raise HTTPException(status_code=503, detail="Website authentication is unavailable")
        tokens = await auth_service.issue_browser_session(user_id)
        response = RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie("devops_access_token", tokens.access_token, httponly=True, samesite="lax")
        response.set_cookie("devops_refresh_token", tokens.refresh_token, httponly=True, samesite="lax")
        return response

    @router.post("/website/login", include_in_schema=False)
    async def website_login(
        request: Request,
        email: str = Form(),
        password: str = Form(),
    ):
        if accounts is None:
            raise HTTPException(status_code=503, detail="Website authentication is unavailable")
        try:
            user_id = await accounts.sign_in(email, password)
        except AccountError:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"title": "Sign in", "mode": "signin", "message": "Invalid email or password."},
                status_code=401,
            )
        return await browser_tokens(user_id)

    @router.post("/website/signup", include_in_schema=False)
    async def website_signup(
        request: Request,
        email: str = Form(),
        password: str = Form(),
    ):
        if accounts is None:
            raise HTTPException(status_code=503, detail="Website authentication is unavailable")
        try:
            user_id = await accounts.sign_up(email, password)
        except AccountError as error:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"title": "Create account", "mode": "signup", "message": str(error)},
                status_code=400,
            )
        return await browser_tokens(user_id)

    @router.post("/v1/website/auth/login")
    async def website_login_json(body: dict[str, str]):
        if accounts is None:
            raise HTTPException(status_code=503, detail="Website authentication is unavailable")
        try:
            user_id = await accounts.sign_in(body.get("email", ""), body.get("password", ""))
        except AccountError as error:
            raise HTTPException(status_code=401, detail="Invalid email or password") from error
        if auth_service is None:
            raise HTTPException(status_code=503, detail="Website authentication is unavailable")
        return (await auth_service.issue_browser_session(user_id)).model_dump()

    return router


__all__ = ["create_website_router"]
