"""Production composition roots for the API and registered Tool Service."""

from __future__ import annotations

import os
from html import escape
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse

from agent_core import AgentRequest, AgentResponse, AgentToolCall
from agent_server.accounts import AccountAlreadyExists, AccountError, LocalAccountService
from agent_server.api.app import create_app
from agent_server.auth import issue_access_token
from agent_server.auth_sessions import AuthSessionService
from agent_server.development_auth import InProcessDeviceApprovalProvider
from agent_server.langgraph_runtime import postgres_runtime
from agent_server.persistence.auth import PostgresAuthRepository
from agent_server.postgres_device_approval import PostgresDeviceApprovalProvider
from agent_server.persistence.postgres import PostgresConversationRepository, create_session_factory
from agent_server.persistence.tool_audit import PostgresToolExecutionRepository
from agent_server.registered_tools import build_default_registry
from agent_server.tool_api import create_tool_service_app
from agent_server.tool_client import RestToolServiceClient
from agent_server.tool_service import ToolService


@dataclass(frozen=True)
class Settings:
    database_url: str
    access_token_secret: str
    public_base_url: str
    tool_service_url: str
    repositories: dict[str, Path]
    auth_mode: str
    development_user_id: str
    runtime: str
    model_provider: str
    model_name: str
    tool_scopes: frozenset[str]

    @classmethod
    def from_environment(cls, *, include_tool_repositories: bool = False) -> "Settings":
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
        runtime = os.getenv("DEVOPS_AGENT_RUNTIME", "langgraph")
        if runtime not in {"langgraph", "echo"}:
            raise RuntimeError("DEVOPS_AGENT_RUNTIME must be langgraph or echo")
        provider = os.getenv("DEVOPS_AGENT_MODEL_PROVIDER", "openai")
        if provider not in {"openai", "groq", "gemini", "ollama"}:
            raise RuntimeError("DEVOPS_AGENT_MODEL_PROVIDER must be openai, groq, gemini, or ollama")
        provider_key = f"{provider.upper()}_API_KEY"
        if provider == "gemini" and os.getenv("GOOGLE_API_KEY"):
            provider_key = "GOOGLE_API_KEY"
        if runtime == "langgraph" and provider != "ollama" and not os.getenv(provider_key):
            raise RuntimeError(f"{provider_key} is required for the selected model provider")
        repositories = (
            _repositories(os.getenv("DEVOPS_AGENT_TOOL_REPOSITORIES", ""))
            if include_tool_repositories
            else {}
        )
        return cls(
            database_url=database_url,
            access_token_secret=secret,
            public_base_url=public_base_url,
            tool_service_url=os.getenv("DEVOPS_AGENT_TOOL_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/"),
            repositories=repositories,
            auth_mode=auth_mode,
            development_user_id=os.getenv("DEVOPS_AGENT_DEVELOPMENT_USER_ID", "developer"),
            runtime=runtime,
            model_provider=provider,
            model_name=os.getenv("DEVOPS_AGENT_MODEL_NAME", "gpt-4o-mini"),
            tool_scopes=frozenset(filter(None, os.getenv("DEVOPS_AGENT_TOOL_SCOPES", "git:read").split(","))),
        )


class DevelopmentEchoRuntime:
    """Deterministic local runtime used only for smoke tests and demos."""
    async def run(self, request: AgentRequest) -> AgentResponse:
        if request.tool_results:
            return AgentResponse(message=f"Tool result: {request.tool_results[-1].get('status', 'unknown')}")
        if request.message.startswith("git status "):
            return AgentResponse(message="", tool_calls=(AgentToolCall("git-status", "git.status", arguments={"repository_id": request.message.removeprefix("git status ").strip()}),))
        return AgentResponse(message=f"Development echo: {request.message}")


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


def _runtime(settings: Settings) -> Any:
    if settings.runtime == "echo":
        return DevelopmentEchoRuntime()
    return PostgresLangGraphRuntime(settings.database_url, _model(settings))


def _model(settings: Settings) -> Any:
    if settings.model_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=settings.model_name)
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
    client = RestToolServiceClient(
        settings.tool_service_url,
        access_token=lambda context: issue_access_token(
            settings.access_token_secret, context.user_id, scopes=settings.tool_scopes
        ),
        allow_insecure_http=_is_development_compose_tool_url(
            settings.tool_service_url, settings.auth_mode
        ),
    )
    app = create_app(runtime=_runtime(settings), conversations=PostgresConversationRepository(sessions), runs=PostgresConversationRepository(sessions), auth_service=auth, tool_executor=client, tool_scopes_for_user=lambda _user: settings.tool_scopes, database_engine=engine)
    if is_local_auth:
        _mount_local_account_approval(app, provider, LocalAccountService(auth_repository))
    else:
        _mount_development_approval(app, provider, settings)
    return app


def create_tool_service_from_environment() -> FastAPI:
    settings = Settings.from_environment(include_tool_repositories=True)
    engine, sessions = create_session_factory(settings.database_url)
    auth = AuthSessionService(repository=PostgresAuthRepository(sessions), approval_provider=InProcessDeviceApprovalProvider(settings.public_base_url), access_token_secret=settings.access_token_secret)
    service = ToolService(build_default_registry(settings.repositories), audit_repository=PostgresToolExecutionRepository(sessions))
    return create_tool_service_app(service=service, auth_service=auth, scopes_for_user=lambda _user: settings.tool_scopes, database_engine=engine)


def _mount_development_approval(app: FastAPI, provider: InProcessDeviceApprovalProvider, settings: Settings) -> None:
    @app.get("/v1/development/device/{approval_id}", response_class=HTMLResponse, include_in_schema=False)
    async def development_device_page(approval_id: str):
        pending = provider.pending(approval_id)
        if pending is None:
            raise HTTPException(404, "Unknown or expired device approval")
        code = escape(pending.user_code)
        user_id = escape(settings.development_user_id, quote=True)
        return f"<h1>DevOps Agent development sign-in</h1><p>Approve sign-in for <b>{user_id}</b> using code <b>{code}</b>.</p><form method='post'><input type='hidden' name='user_code' value='{code}'><button name='decision' value='approve'>Approve</button><button name='decision' value='deny'>Deny</button></form>"

    @app.post("/v1/development/device/{approval_id}", response_class=HTMLResponse, include_in_schema=False)
    async def development_device_decision(approval_id: str, user_code: str = Form(), decision: str = Form()):
        if not provider.decide(approval_id, user_code=user_code, user_id=settings.development_user_id, approved=decision == "approve"):
            raise HTTPException(400, "Invalid or expired approval")
        return "<h1>Device decision recorded</h1><p>You may return to the CLI.</p>"


def _mount_local_account_approval(
    app: FastAPI,
    provider: PostgresDeviceApprovalProvider,
    accounts: LocalAccountService,
) -> None:
    def render_form(approval_id: str, user_code: str, mode: str, message: str = ""):
        title = "Create your account" if mode == "signup" else "Sign in"
        submit = "Create account" if mode == "signup" else "Sign in"
        notice = f"<p role='alert'>{escape(message)}</p>" if message else ""
        html = (
            "<!doctype html><html><head><meta charset='utf-8'><title>DevOps Agent account</title>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'></head><body>"
            f"<h1>{title}</h1>{notice}"
            "<p>This self-hosted account flow requires no external identity provider. "
            "Email verification and password recovery are not configured.</p>"
            f"<nav><a href='?user_code={escape(user_code, quote=True)}&amp;mode=signin'>Sign in</a> · "
            f"<a href='?user_code={escape(user_code, quote=True)}&amp;mode=signup'>Create account</a></nav>"
            f"<form method='post' action='/v1/auth/device/verify/{escape(approval_id, quote=True)}'>"
            f"<input type='hidden' name='user_code' value='{escape(user_code, quote=True)}'>"
            f"<input type='hidden' name='mode' value='{escape(mode, quote=True)}'>"
            "<label>Email <input type='email' name='email' autocomplete='email' required maxlength='254'></label><br>"
            f"<label>Password <input type='password' name='password' autocomplete='{'new-password' if mode == 'signup' else 'current-password'}' "
            "required minlength='12' maxlength='1024'></label><br>"
            f"<button type='submit'>{submit}</button></form></body></html>"
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

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
    async def local_account_page(approval_id: str, user_code: str, mode: str | None = None):
        pending = await pending_request(approval_id, user_code)
        selected_mode = mode if mode in {"signin", "signup"} else pending.mode.value
        return render_form(approval_id, user_code, selected_mode)

    @app.post(
        "/v1/auth/device/verify/{approval_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def local_account_decision(
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
            response = render_form(approval_id, user_code, mode, str(error))
            response.status_code = 409
            return response
        except AccountError as error:
            status_code = 401 if mode == "signin" else 400
            response = render_form(approval_id, user_code, mode, str(error))
            response.status_code = status_code
            return response
        if not await provider.decide(
            approval_id, user_code=user_code, user_id=user_id, approved=True
        ):
            raise HTTPException(400, "Device authorization expired; start again")
        return HTMLResponse(
            "<!doctype html><h1>Signed in successfully</h1>"
            "<p>You may return to the DevOps Agent CLI.</p>",
            headers={"Cache-Control": "no-store"},
        )


def _repositories(value: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if not value:
        return result
    for item in value.split(","):
        name, separator, raw_path = item.partition("=")
        path = Path(raw_path).expanduser().resolve()
        if not separator or not name or not path.is_dir():
            raise RuntimeError("DEVOPS_AGENT_TOOL_REPOSITORIES must be comma-separated name=existing-directory entries")
        result[name] = path
    return result


def _is_development_compose_tool_url(value: str, auth_mode: str) -> bool:
    parsed = urlsplit(value)
    return (
        auth_mode in {"development", "local"}
        and parsed.scheme == "http"
        and parsed.hostname == "tool-service"
        and parsed.port == 8001
        and parsed.username is None
        and parsed.password is None
    )


__all__ = ["Settings", "create_api_from_environment", "create_tool_service_from_environment"]
