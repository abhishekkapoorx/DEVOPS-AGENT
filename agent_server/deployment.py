"""Production composition root for the server API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from agent_core import AgentRequest, AgentResponse
from agent_server.accounts import AccountAlreadyExists, AccountError, LocalAccountService
from agent_server.api.app import create_app
from agent_server.auth_sessions import AuthSessionService
from agent_server.web_templates import create_site_templates
from agent_server.conversation_titles import ModelConversationTitleGenerator
from agent_server.development_auth import InProcessDeviceApprovalProvider
from agent_server.langgraph_runtime import postgres_runtime
from agent_server.persistence.auth import PostgresAuthRepository
from agent_server.postgres_device_approval import PostgresDeviceApprovalProvider
from agent_server.persistence.postgres import PostgresConversationRepository, create_session_factory
from agent_server.local_tool_broker import LocalToolBroker
from agent_server.persistence.secrets import SecretRepository
from agent_server.secrets import SecretBox, SecretConfigurationError


@dataclass(frozen=True)
class Settings:
    database_url: str
    access_token_secret: str
    public_base_url: str
    auth_mode: str
    development_user_id: str
    model_provider: str
    model_name: str
    model_base_url: str | None
    webhook_token: str | None
    encryption_key: str | None

    @classmethod
    def from_environment(cls) -> "Settings":
        required = ("DATABASE_URL", "DEVOPS_AGENT_ACCESS_TOKEN_SECRET", "DEVOPS_AGENT_PUBLIC_BASE_URL")
        missing = [key for key in required if not os.environ.get(key)]
        if missing:
            raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")
        database_url = os.environ["DATABASE_URL"]
        if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
        secret = os.environ["DEVOPS_AGENT_ACCESS_TOKEN_SECRET"]
        if len(secret) < 32:
            raise RuntimeError("DEVOPS_AGENT_ACCESS_TOKEN_SECRET must contain at least 32 characters")
        auth_mode = os.getenv("DEVOPS_AGENT_AUTH_MODE", "")
        if auth_mode not in {"development", "local"}:
            raise RuntimeError("DEVOPS_AGENT_AUTH_MODE must be development or local; configure a website provider for production")
        public_base_url = os.environ["DEVOPS_AGENT_PUBLIC_BASE_URL"].rstrip("/")
        parsed_public_url = urlsplit(public_base_url)
        if (
            not parsed_public_url.scheme
            or not parsed_public_url.hostname
            or parsed_public_url.username is not None
            or parsed_public_url.password is not None
        ):
            raise RuntimeError("DEVOPS_AGENT_PUBLIC_BASE_URL must be an absolute HTTP(S) URL")
        local_http = parsed_public_url.scheme == "http" and parsed_public_url.hostname in {
            "localhost", "127.0.0.1", "::1"
        }
        if auth_mode == "local" and parsed_public_url.scheme != "https" and not local_http:
            raise RuntimeError("Local email/password auth requires HTTPS except on localhost")
        if os.getenv("DEVOPS_AGENT_ENABLE_MCP_AGENTS", "false").strip().lower() in {"1", "true", "yes", "on"}:
            raise RuntimeError("AWS/GCP MCP agents are disabled; MCP support is planned for a future release")
        provider = os.getenv("DEVOPS_AGENT_MODEL_PROVIDER", "openai")
        if provider not in {"openai", "groq", "gemini", "ollama"}:
            raise RuntimeError("DEVOPS_AGENT_MODEL_PROVIDER must be openai, groq, gemini, or ollama")
        provider_key = f"{provider.upper()}_API_KEY"
        if provider == "gemini" and os.getenv("GOOGLE_API_KEY"):
            provider_key = "GOOGLE_API_KEY"
        if provider != "ollama" and not os.getenv(provider_key):
            raise RuntimeError(f"{provider_key} is required for the selected model provider")
        return cls(
            database_url=database_url,
            access_token_secret=secret,
            public_base_url=public_base_url,
            auth_mode=auth_mode,
            development_user_id=os.getenv("DEVOPS_AGENT_DEVELOPMENT_USER_ID", "developer"),
            model_provider=provider,
            model_name=os.getenv("DEVOPS_AGENT_MODEL_NAME", "gpt-4o-mini"),
            model_base_url=os.getenv("DEVOPS_AGENT_MODEL_BASE_URL") or None,
            webhook_token=os.getenv("WEBHOOK_TOKEN") or None,
            encryption_key=os.getenv("ENCRYPTION_KEY") or None,
        )


class PostgresLangGraphRuntime:
    """Open a Postgres-backed LangGraph checkpoint saver for every durable turn.

    The saver is intentionally scoped to a turn so workers can be restarted or
    scaled independently. Checkpoints remain keyed by conversation in Postgres.
    """
    def __init__(self, database_url: str, model: Any) -> None:
        self.database_url, self.model = database_url, model

    async def run(self, request: AgentRequest) -> AgentResponse:
        async with postgres_runtime(self.database_url, model=self.model) as runtime:
            return await runtime.run(request)


def _runtime(settings: Settings, model: Any | None = None) -> Any:
    selected_model = model if model is not None else _model(settings)
    return PostgresLangGraphRuntime(settings.database_url, selected_model)


def _model(settings: Settings) -> Any:
    if settings.model_provider == "openai":
        from langchain_openai import ChatOpenAI
        kwargs = {"model": settings.model_name}
        if settings.model_base_url:
            kwargs["base_url"] = settings.model_base_url
        return ChatOpenAI(**kwargs)
    if settings.model_provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=settings.model_name)
    if settings.model_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=settings.model_name)
    from langchain_ollama import ChatOllama
    return ChatOllama(model=settings.model_name)


def create_api_from_environment() -> FastAPI:
    settings = Settings.from_environment()
    engine, sessions = create_session_factory(settings.database_url)
    auth_repository = PostgresAuthRepository(sessions)
    is_local_auth = settings.auth_mode == "local"
    provider = (
        PostgresDeviceApprovalProvider(auth_repository, settings.public_base_url)
        if is_local_auth
        else InProcessDeviceApprovalProvider(settings.public_base_url)
    )
    auth = AuthSessionService(repository=auth_repository, approval_provider=provider, access_token_secret=settings.access_token_secret)
    local_tools = LocalToolBroker()
    model = _model(settings)
    secret_repository = None
    account_service = LocalAccountService(auth_repository)
    if settings.encryption_key:
        try:
            secret_repository = SecretRepository(sessions, SecretBox.from_environment())
        except SecretConfigurationError as error:
            raise RuntimeError(f"Invalid ENCRYPTION_KEY configuration: {error}") from error
    app = create_app(
        runtime=_runtime(settings, model),
        conversations=PostgresConversationRepository(sessions),
        runs=PostgresConversationRepository(sessions),
        auth_service=auth,
        conversation_title_generator=ModelConversationTitleGenerator(model),
        tool_executor=local_tools,
        local_tool_broker=local_tools,
        database_engine=engine,
        database_sessions=sessions,
        webhook_token=settings.webhook_token,
        secret_repository=secret_repository,
        website_accounts=account_service,
    )
    if is_local_auth:
        _mount_local_account_approval(app, provider, account_service, auth)
    else:
        _mount_development_approval(app, provider, settings, auth)
    return app


def _mount_development_approval(
    app: FastAPI,
    provider: InProcessDeviceApprovalProvider,
    settings: Settings,
    auth_service: AuthSessionService | None = None,
) -> None:
    templates = create_site_templates(Path(__file__).with_name("templates"), auth_service)

    @app.get("/v1/development/device/{approval_id}", response_class=HTMLResponse, include_in_schema=False)
    async def development_device_page(request: Request, approval_id: str):
        pending = provider.pending(approval_id)
        if pending is None:
            raise HTTPException(404, "Unknown or expired device approval")
        return templates.TemplateResponse(
            request=request,
            name="device_approval.html",
            context={
                "title": "Development sign-in",
                "user_code": pending.user_code,
                "user_id": settings.development_user_id,
                "action_url": request.url.path,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/v1/development/device/{approval_id}", response_class=HTMLResponse, include_in_schema=False)
    async def development_device_decision(request: Request, approval_id: str, user_code: str = Form(), decision: str = Form()):
        if not provider.decide(approval_id, user_code=user_code, user_id=settings.development_user_id, approved=decision == "approve"):
            raise HTTPException(400, "Invalid or expired approval")
        return templates.TemplateResponse(
            request=request,
            name="status_page.html",
            context={
                "title": "Device decision recorded",
                "eyebrow": "Device approval",
                "heading": "Device decision recorded",
                "message": "You may return to the DevOps Agent CLI.",
            },
            headers={"Cache-Control": "no-store"},
        )


def _mount_local_account_approval(
    app: FastAPI,
    provider: PostgresDeviceApprovalProvider,
    accounts: LocalAccountService,
    auth_service: AuthSessionService | None = None,
) -> None:
    templates = create_site_templates(Path(__file__).with_name("templates"), auth_service)

    def render_form(request: Request, approval_id: str, user_code: str, mode: str, message: str = ""):
        page_url = request.url_for("local_account_page", approval_id=approval_id)
        return templates.TemplateResponse(
            request=request,
            name="account_auth.html",
            context={
                "title": "Create your account" if mode == "signup" else "Sign in",
                "submit_label": "Create account" if mode == "signup" else "Sign in",
                "password_autocomplete": "new-password" if mode == "signup" else "current-password",
                "password_hint": "Use at least 12 characters." if mode == "signup" else "Enter the password for your account.",
                "approval_id": approval_id,
                "user_code": user_code,
                "mode": mode,
                "message": message,
                "action_url": page_url,
                "signin_url": page_url.include_query_params(user_code=user_code, mode="signin"),
                "signup_url": page_url.include_query_params(user_code=user_code, mode="signup"),
            },
            headers={"Cache-Control": "no-store"},
        )

    async def pending_request(approval_id: str, user_code: str):
        pending = await provider.pending(approval_id)
        if (
            pending is None
            or pending.user_code != user_code
            or pending.expires_at <= datetime.now(pending.expires_at.tzinfo or timezone.utc)
        ):
            raise HTTPException(404, "Unknown or expired device authorization")
        return pending

    @app.get(
        "/v1/auth/device/verify/{approval_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def local_account_page(
        request: Request, approval_id: str, user_code: str, mode: str | None = None
    ):
        pending = await pending_request(approval_id, user_code)
        selected_mode = mode if mode in {"signin", "signup"} else pending.mode.value
        return render_form(request, approval_id, user_code, selected_mode)

    @app.post(
        "/v1/auth/device/verify/{approval_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def local_account_decision(
        request: Request,
        approval_id: str,
        user_code: str = Form(min_length=8, max_length=16),
        mode: str | None = Form(default=None),
        email: str = Form(min_length=3, max_length=254),
        password: str = Form(min_length=1, max_length=1024),
    ):
        pending = await pending_request(approval_id, user_code)
        mode = mode or pending.mode.value
        if mode not in {"signin", "signup"}:
            raise HTTPException(400, "Invalid account action")
        try:
            if mode == "signup":
                user_id = await accounts.sign_up(email, password)
            else:
                user_id = await accounts.sign_in(email, password)
        except AccountAlreadyExists as error:
            response = render_form(request, approval_id, user_code, mode, str(error))
            response.status_code = 409
            return response
        except AccountError as error:
            status_code = 401 if mode == "signin" else 400
            response = render_form(request, approval_id, user_code, mode, str(error))
            response.status_code = status_code
            return response
        if not await provider.decide(
            approval_id, user_code=user_code, user_id=user_id, approved=True
        ):
            raise HTTPException(400, "Device authorization expired; start again")
        if auth_service is not None:
            tokens = await auth_service.issue_browser_session(user_id)
            response = RedirectResponse("/settings", status_code=303)
            response.set_cookie("devops_access_token", tokens.access_token, httponly=True, samesite="lax")
            response.set_cookie("devops_refresh_token", tokens.refresh_token, httponly=True, samesite="lax")
            return response
        return templates.TemplateResponse(
            request=request,
            name="status_page.html",
            context={
                "title": "Signed in successfully",
                "eyebrow": "Account",
                "heading": "Signed in successfully",
                "message": "You may return to the DevOps Agent CLI.",
            },
            headers={"Cache-Control": "no-store"},
        )


__all__ = ["Settings", "create_api_from_environment"]
