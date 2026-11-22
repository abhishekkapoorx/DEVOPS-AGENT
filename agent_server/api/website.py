"""Public landing page and browser sign-in entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from agent_server.alertmanager_manifests import helm_values, kustomize_bundle, operator_manifest
from agent_server.accounts import AccountError, LocalAccountService
from agent_server.auth_sessions import AuthSessionService
from agent_server.docs import DOCS, load_doc
from agent_server.web_templates import create_site_templates


def create_website_router(
    template_dir: Path,
    *,
    accounts: LocalAccountService | None = None,
    auth_service: AuthSessionService | None = None,
) -> APIRouter:
    router = APIRouter()
    templates = create_site_templates(template_dir, auth_service)
    docs_dir = template_dir.parent / "docs" / "website"
    static_files = StaticFiles(directory=template_dir.parent / "static")

    @router.get("/static/{asset_path:path}", include_in_schema=False)
    async def static_asset(request: Request, asset_path: str):
        return await static_files.get_response(asset_path, request.scope)

    @router.get("/", include_in_schema=False)
    async def landing_page(request: Request):
        authenticated = bool(
            auth_service
            and auth_service.current_user(request.cookies.get("devops_access_token", ""))
        )
        return templates.TemplateResponse(
            request=request,
            name="landing.html",
            context={"title": "Trustworthy incident investigations", "authenticated": authenticated},
        )

    @router.get("/login", include_in_schema=False)
    async def login_page(request: Request, mode: str = "signin"):
        if auth_service is not None:
            user = auth_service.current_user(request.cookies.get("devops_access_token", ""))
            if user is not None:
                return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"title": "Sign in", "mode": mode if mode in {"signin", "signup"} else "signin", "message": None},
        )

    @router.get("/docs/downloads/alertmanager/{manifest_format}", include_in_schema=False)
    async def download_alertmanager_example(manifest_format: str):
        endpoint = "https://YOUR_AGENT_HOST/webhook/alertmanager"
        token = "REPLACE_WITH_WEBHOOK_TOKEN"
        if manifest_format == "kustomize.zip":
            return Response(
                content=kustomize_bundle(endpoint, token),
                media_type="application/zip",
                headers={
                    "Content-Disposition": 'attachment; filename="alertmanager-webhook-kustomize-example.zip"'
                },
            )
        if manifest_format == "helm.yaml":
            content = helm_values(endpoint, token)
            filename = "alertmanager-webhook-values-example.yaml"
        elif manifest_format == "operator.yaml":
            content = operator_manifest(endpoint, token)
            filename = "alertmanagerconfig-example.yaml"
        else:
            raise HTTPException(status_code=404, detail="Manifest example not found")
        return Response(
            content=content,
            media_type="application/yaml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/docs/{slug:path}", include_in_schema=False)
    async def documentation_page(request: Request, slug: str):
        loaded = load_doc(slug, docs_dir)
        if loaded is None:
            raise HTTPException(status_code=404, detail="Documentation page not found")
        page, html, index = loaded
        previous_page = DOCS[index - 1] if index else None
        next_page = DOCS[index + 1] if index + 1 < len(DOCS) else None
        return templates.TemplateResponse(
            request=request,
            name="documentation.html",
            context={
                "title": page["title"],
                "docs": DOCS,
                "active_slug": page["slug"],
                "doc_title": page["title"],
                "doc_html": html,
                "previous_page": previous_page,
                "next_page": next_page,
            },
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
        if auth_service is not None:
            user = auth_service.current_user(request.cookies.get("devops_access_token", ""))
            if user is not None:
                return RedirectResponse("/settings", status_code=status.HTTP_303_SEE_OTHER)
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

    @router.get("/account", include_in_schema=False)
    async def account_page(request: Request):
        if accounts is None or auth_service is None:
            raise HTTPException(status_code=503, detail="Website authentication is unavailable")
        user = auth_service.current_user(request.cookies.get("devops_access_token", ""))
        if user is None:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        account = await accounts.get_profile(user.user_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        return templates.TemplateResponse(
            request=request,
            name="account.html",
            context={"title": "Account", "account": account, "message": None},
        )

    @router.post("/account", include_in_schema=False)
    async def update_account(request: Request, display_name: str = Form(default="")):
        if accounts is None or auth_service is None:
            raise HTTPException(status_code=503, detail="Website authentication is unavailable")
        user = auth_service.current_user(request.cookies.get("devops_access_token", ""))
        if user is None:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        try:
            account = await accounts.update_profile(user.user_id, display_name)
        except AccountError as error:
            account = await accounts.get_profile(user.user_id)
            if account is None:
                raise HTTPException(status_code=404, detail="Account not found")
            return templates.TemplateResponse(
                request=request,
                name="account.html",
                context={"title": "Account", "account": account, "message": str(error)},
                status_code=400,
            )
        return templates.TemplateResponse(
            request=request,
            name="account.html",
            context={"title": "Account", "account": account, "message": "Account details updated."},
        )

    return router


__all__ = ["create_website_router"]
