import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.deployment import Settings, _mount_development_approval
from agent_server.development_auth import DevelopmentApprovalProvider


def _set_valid_settings(monkeypatch, **overrides):
    values = {
        "DATABASE_URL": "postgresql://devops:devops@localhost/devops",
        "DEVOPS_AGENT_ACCESS_TOKEN_SECRET": "x" * 40,
        "DEVOPS_AGENT_PUBLIC_BASE_URL": "http://127.0.0.1:8000",
        "DEVOPS_AGENT_AUTH_MODE": "development",
        "DEVOPS_AGENT_MODEL_PROVIDER": "ollama",
        "DEVOPS_AGENT_ENABLE_MCP_AGENTS": "false",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_settings_load_current_backend_configuration(monkeypatch):
    _set_valid_settings(monkeypatch)

    settings = Settings.from_environment()

    assert settings.database_url == "postgresql://devops:devops@localhost/devops"
    assert settings.auth_mode == "development"
    assert settings.model_provider == "ollama"
    assert settings.model_name == "gpt-4o-mini"


def test_settings_require_postgres_and_a_long_access_token_secret(monkeypatch):
    _set_valid_settings(monkeypatch, DATABASE_URL="sqlite:///local.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        Settings.from_environment()

    _set_valid_settings(monkeypatch, DEVOPS_AGENT_ACCESS_TOKEN_SECRET="short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        Settings.from_environment()


def test_settings_require_provider_credentials_except_for_ollama(monkeypatch):
    _set_valid_settings(
        monkeypatch,
        DEVOPS_AGENT_MODEL_PROVIDER="openai",
        OPENAI_API_KEY="",
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        Settings.from_environment()


def test_settings_reject_unknown_providers_and_unsupported_mcp_agents(monkeypatch):
    _set_valid_settings(monkeypatch, DEVOPS_AGENT_MODEL_PROVIDER="unknown")
    with pytest.raises(RuntimeError, match="MODEL_PROVIDER"):
        Settings.from_environment()

    _set_valid_settings(monkeypatch, DEVOPS_AGENT_ENABLE_MCP_AGENTS="true")
    with pytest.raises(RuntimeError, match="MCP support is planned"):
        Settings.from_environment()


def test_local_auth_requires_https_outside_loopback(monkeypatch):
    _set_valid_settings(
        monkeypatch,
        DEVOPS_AGENT_AUTH_MODE="local",
        DEVOPS_AGENT_PUBLIC_BASE_URL="http://agent.example.com",
    )

    with pytest.raises(RuntimeError, match="requires HTTPS"):
        Settings.from_environment()


def test_development_approval_provider_completes_a_device_decision():
    provider = DevelopmentApprovalProvider("http://127.0.0.1:8000")
    presentation = asyncio.run(provider.create_device_authorization(
        device_code="device",
        user_code="ABCD-1234",
        mode="signin",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    ))

    assert presentation.verification_url.endswith(presentation.approval_id)
    assert provider.decide(
        presentation.approval_id,
        user_code="ABCD-1234",
        user_id="dev",
        approved=True,
    )
    approval = asyncio.run(provider.get_device_approval(presentation.approval_id))
    assert approval.user_id == "dev"


def test_development_approval_page_escapes_identity_and_ignores_form_identity():
    provider = DevelopmentApprovalProvider("http://localhost:8000")
    presentation = asyncio.run(provider.create_device_authorization(
        device_code="device",
        user_code="ABCD-1234",
        mode="signin",
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
    approval = asyncio.run(provider.get_device_approval(presentation.approval_id))
    assert approval.user_id == "<developer> & admin"
