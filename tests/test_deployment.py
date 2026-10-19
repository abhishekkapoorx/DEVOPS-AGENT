from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from agent_server.api.app import create_app
from agent_server.auth import issue_access_token
from agent_server.auth_sessions import (
    AuthSessionService, DeviceApproval, DeviceStatus,
)
from agent_server.deployment import (
    Settings,
    _is_development_compose_tool_url,
    _mount_development_approval,
)
from agent_server.development_auth import DevelopmentApprovalProvider
from agent_server.persistence.memory import InMemoryConversationRepository
from agent_server.registered_tools import build_default_registry
from agent_server.tool_api import create_tool_service_app
from agent_server.tool_client import RestToolServiceClient
from agent_server.tool_service import ToolService


class MemoryAuthRepository:
    def __init__(self):
        self.devices = {}
        self.sessions = {}

    async def create_device(self, device):
        self.devices[device.device_code] = device

    async def get_device(self, device_code):
        return self.devices.get(device_code)

    async def update_device(self, device):
        self.devices[device.device_code] = device

    async def complete_device(self, device, session):
        current = self.devices.get(device.device_code)
        if current is None or current.status is not DeviceStatus.PENDING:
            return False
        self.devices[device.device_code] = device
        self.sessions[session.session_id] = session
        return True

    async def get_session_by_refresh_hash(self, token_hash):
        return next((item for item in self.sessions.values() if item.refresh_hash == token_hash), None)

    async def rotate_session(self, old, replacement, at):
        current = self.sessions.get(old.session_id)
        if current is None or current.revoked_at is not None:
            return False
        self.sessions[old.session_id] = current.model_copy(update={"revoked_at": at, "replaced_by": replacement.session_id})
        self.sessions[replacement.session_id] = replacement
        return True

    async def revoke_session_family(self, family_id, at):
        for key, session in self.sessions.items():
            if session.family_id == family_id:
                self.sessions[key] = session.model_copy(update={"revoked_at": at})


class ClientResponseAdapter:
    def __init__(self, response):
        self.status = response.status_code
        self._content = response.content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, limit):
        return self._content[:limit]


def test_local_api_to_separate_tool_service_round_trip_and_reconnect():
    secret = "integration-test-secret-with-at-least-32-bytes"
    repository = InMemoryConversationRepository()
    auth_repository = MemoryAuthRepository()
    approval_provider = DevelopmentApprovalProvider("http://localhost")
    auth = AuthSessionService(
        repository=auth_repository,
        approval_provider=approval_provider,
        access_token_secret=secret,
        poll_interval=1,
    )
    tool_app = create_tool_service_app(
        service=ToolService(build_default_registry({"workspace": Path.cwd()})),
        auth_service=auth,
    )
    tool_http = TestClient(tool_app)
    def tool_opener(request, timeout):
        if request.method == "GET":
            response = tool_http.get(
                "/v1/tools", headers=dict(request.header_items())
            )
        else:
            response = tool_http.post(
                "/v1/tool-calls",
                headers=dict(request.header_items()),
                content=request.data,
            )
        if response.status_code >= 400:
            from urllib.error import HTTPError
            raise HTTPError(request.full_url, response.status_code, "Tool Service error", response.headers, None)
        return ClientResponseAdapter(response)

    tool_client = RestToolServiceClient(
        "http://localhost:8001",
        access_token=lambda context: issue_access_token(secret, context.user_id, scopes=context.scopes),
        opener=tool_opener,
    )
    from agent_server.deployment import DevelopmentEchoRuntime
    api = create_app(
        runtime=DevelopmentEchoRuntime(),
        conversations=repository,
        runs=repository,
        auth_service=auth,
        tool_executor=tool_client,
        tool_scopes_for_user=lambda _user: frozenset({"git:read"}),
    )
    _mount_development_approval(api, approval_provider, SimpleNamespace(development_user_id="e2e-user"))
    client = TestClient(api)

    challenge = client.post("/v1/auth/device", json={"mode": "signin"}).json()
    approval_id = challenge["verification_url"].rsplit("/", 1)[-1]
    approved = client.post(
        f"/v1/development/device/{approval_id}",
        data={"user_code": challenge["user_code"], "decision": "approve"},
    )
    token_response = client.post(
        "/v1/auth/device/poll", json={"device_code": challenge["device_code"]}
    ).json()
    access_token = token_response["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    conversation_id = client.post("/v1/conversations", headers=headers, json={"title": "E2E"}).json()["id"]
    turn = client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={**headers, "Idempotency-Key": "e2e-turn-1"},
        json={"content": "git status workspace"},
    ).json()
    reconnected = client.get(f"/v1/runs/{turn['run_id']}", headers=headers).json()
    messages = client.get(f"/v1/conversations/{conversation_id}/messages", headers=headers).json()

    assert approved.status_code == 200
    assert reconnected["status"] == "completed", reconnected
    assert reconnected["tool_calls"][0]["result"]["status"] == "succeeded"
    assert messages[-1]["content"].startswith("Tool result: succeeded")


def run(coro):
    return asyncio.run(coro)


def test_development_approval_provider_completes_a_device_decision():
    provider = DevelopmentApprovalProvider("http://127.0.0.1:8000")
    presentation = run(provider.create_device_authorization(
        device_code="device", user_code="ABCD-1234", mode="signin",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    ))

    assert presentation.verification_url.endswith(presentation.approval_id)
    assert provider.decide(presentation.approval_id, user_code="ABCD-1234", user_id="dev", approved=True)
    assert run(provider.get_device_approval(presentation.approval_id)).user_id == "dev"


def test_settings_rejects_unsafe_or_incomplete_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///not-postgres")
    monkeypatch.setenv("DEVOPS_AGENT_ACCESS_TOKEN_SECRET", "x" * 32)
    monkeypatch.setenv("DEVOPS_AGENT_PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("DEVOPS_AGENT_AUTH_MODE", "development")
    monkeypatch.setenv("DEVOPS_AGENT_RUNTIME", "echo")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        Settings.from_environment()


def test_settings_supports_repeatable_echo_smoke_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://devops:devops@localhost/devops")
    monkeypatch.setenv("DEVOPS_AGENT_ACCESS_TOKEN_SECRET", "x" * 32)
    monkeypatch.setenv("DEVOPS_AGENT_PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("DEVOPS_AGENT_AUTH_MODE", "development")
    monkeypatch.setenv("DEVOPS_AGENT_RUNTIME", "echo")
    workspace = Path.cwd().resolve()
    monkeypatch.setenv("DEVOPS_AGENT_TOOL_REPOSITORIES", f"workspace={workspace}")

    settings = Settings.from_environment(include_tool_repositories=True)

    assert settings.runtime == "echo"
    assert settings.repositories == {"workspace": workspace}


def test_local_auth_requires_https_outside_loopback(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://devops:devops@localhost/devops")
    monkeypatch.setenv("DEVOPS_AGENT_ACCESS_TOKEN_SECRET", "x" * 32)
    monkeypatch.setenv("DEVOPS_AGENT_PUBLIC_BASE_URL", "http://agent.example.com")
    monkeypatch.setenv("DEVOPS_AGENT_AUTH_MODE", "local")
    monkeypatch.setenv("DEVOPS_AGENT_RUNTIME", "echo")

    with pytest.raises(RuntimeError, match="requires HTTPS"):
        Settings.from_environment()


def test_api_settings_do_not_require_tool_repository_mount(monkeypatch):
    from uuid import uuid4

    missing_repository = Path.cwd() / f"missing-repository-{uuid4().hex}"
    monkeypatch.setenv("DATABASE_URL", "postgresql://devops:devops@localhost/devops")
    monkeypatch.setenv("DEVOPS_AGENT_ACCESS_TOKEN_SECRET", "x" * 32)
    monkeypatch.setenv("DEVOPS_AGENT_PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("DEVOPS_AGENT_AUTH_MODE", "development")
    monkeypatch.setenv("DEVOPS_AGENT_RUNTIME", "echo")
    monkeypatch.setenv("DEVOPS_AGENT_TOOL_REPOSITORIES", f"workspace={missing_repository}")

    settings = Settings.from_environment()

    assert settings.repositories == {}


def test_only_development_compose_tool_url_uses_http():
    assert _is_development_compose_tool_url("http://tool-service:8001", "development")
    assert not _is_development_compose_tool_url("http://other-service:8001", "development")
    assert not _is_development_compose_tool_url("http://tool-service:8001", "production")


def test_development_approval_page_escapes_configured_identity_and_ignores_form_identity():
    provider = DevelopmentApprovalProvider("http://localhost:8000")
    presentation = run(provider.create_device_authorization(
        device_code="device", user_code="ABCD-1234", mode="signin",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    ))
    app = FastAPI()
    _mount_development_approval(
        app, provider, SimpleNamespace(development_user_id="<developer> & admin")
    )
    client = TestClient(app)

    page = client.get(f"/v1/development/device/{presentation.approval_id}")
    decision = client.post(
        f"/v1/development/device/{presentation.approval_id}",
        data={"user_code": "ABCD-1234", "decision": "approve", "user_id": "attacker"},
    )

    assert "&lt;developer&gt; &amp; admin" in page.text
    assert decision.status_code == 200
    assert run(provider.get_device_approval(presentation.approval_id)).user_id == "<developer> & admin"
