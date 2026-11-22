from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.api.settings import create_settings_router
from agent_server.auth import issue_access_token
from agent_server.auth_sessions import AuthSessionService
from agent_server.integrations import (
    IntegrationSlackDestinationResolver,
    IntegrationValidationError,
    validate_slack_webhook_url,
)
from agent_server.investigations.slack import build_test_briefing
from tests.test_auth_sessions import MemoryAuthRepository


VALID_URL = "https://hooks.slack.com/services/T000/B000/abcdEFGH"


class FakeIntegration:
    def __init__(self, owner_user_id: str, provider: str, display_name: str, url: str, enabled: bool):
        self.id = f"{owner_user_id}-{provider}"
        self.owner_user_id = owner_user_id
        self.provider = provider
        self.display_name = display_name
        self.enabled = enabled
        self.webhook_url = url
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeSecretRepository:
    def __init__(self):
        self.integrations: dict[tuple[str, str], FakeIntegration] = {}
        self.webhooks = []
        self.resources = []

    async def create_webhook_secret(self, user_id, name):
        row = SimpleNamespace(id="webhook-1", user_id=user_id, name=name, created_at=datetime.now(timezone.utc), last_used_at=None)
        self.webhooks.append(row)
        return row, "whsec_once"

    async def list_webhook_secrets(self, user_id):
        return self.webhooks

    async def revoke_webhook_secret(self, user_id, secret_id):
        return True

    async def save_resource_secret(self, user_id, provider, name, value):
        row = SimpleNamespace(id="resource-1", provider=provider, name=name, updated_at=datetime.now(timezone.utc))
        self.resources.append(row)
        return row

    async def list_resource_secrets(self, user_id):
        return self.resources

    async def delete_resource_secret(self, user_id, secret_id):
        return True

    async def save_integration(self, owner_user_id, provider, display_name, webhook_url, enabled):
        row = FakeIntegration(owner_user_id, provider, display_name, webhook_url, enabled)
        self.integrations[(owner_user_id, provider)] = row
        return row

    async def list_integrations(self, owner_user_id):
        return [row for (user_id, _), row in self.integrations.items() if user_id == owner_user_id]

    async def get_integration(self, owner_user_id, provider):
        return self.integrations.get((owner_user_id, provider))

    async def decrypt_integration_webhook_url(self, row):
        return row.webhook_url

    async def delete_integration(self, owner_user_id, provider):
        return self.integrations.pop((owner_user_id, provider), None) is not None


def _client(user_id: str = "user-1"):
    auth = AuthSessionService(
        repository=MemoryAuthRepository(),
        approval_provider=object(),
        access_token_secret="test-secret",
    )
    app = FastAPI()
    store = FakeSecretRepository()
    app.include_router(
        create_settings_router(
            sessions=lambda: None,
            secret_repository=store,
            auth_service=auth,
            template_dir=Path("agent_server/templates"),
        )
    )
    client = TestClient(app, cookies={"devops_access_token": issue_access_token("test-secret", user_id)})
    return client, store


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.slack.com/services/T000/B000/abcd",
        "https://evil.example/services/T000/B000/abcd",
        "https://hooks.slack.com/",
        "https://user:pass@hooks.slack.com/services/T000/B000/abcd",
        "https://hooks.slack.com/services/T000/B000/abcd?token=x",
        "",
    ],
)
def test_slack_webhook_url_validation_rejects_unsafe_urls(url):
    with pytest.raises(IntegrationValidationError):
        validate_slack_webhook_url(url)


def test_slack_webhook_url_validation_accepts_incoming_webhook():
    assert validate_slack_webhook_url(f"  {VALID_URL}  ") == VALID_URL


@pytest.mark.asyncio
async def test_integration_resolver_ignores_missing_and_disabled_integrations():
    store = FakeSecretRepository()
    resolver = IntegrationSlackDestinationResolver(store)

    assert await resolver.webhook_url_for("user-1") is None
    await store.save_integration("user-1", "slack", "Slack", VALID_URL, False)
    assert await resolver.webhook_url_for("user-1") is None
    await store.save_integration("user-1", "slack", "Slack", VALID_URL, True)
    assert await resolver.webhook_url_for("user-1") == VALID_URL
    assert await resolver.webhook_url_for("user-2") is None


def test_integrations_page_requires_sign_in():
    auth = AuthSessionService(
        repository=MemoryAuthRepository(),
        approval_provider=object(),
        access_token_secret="test-secret",
    )
    app = FastAPI()
    app.include_router(
        create_settings_router(
            sessions=lambda: None,
            secret_repository=FakeSecretRepository(),
            auth_service=auth,
            template_dir=Path("agent_server/templates"),
        )
    )

    response = TestClient(app).get("/settings/integrations", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_save_slack_integration_masks_url_and_scopes_to_owner():
    client, store = _client()

    response = client.post(
        "/settings/integrations",
        data={"display_name": "On-call", "webhook_url": VALID_URL, "enabled": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/settings/integrations"
    saved = store.integrations[("user-1", "slack")]
    assert saved.display_name == "On-call"
    assert saved.enabled is True
    assert saved.webhook_url == VALID_URL

    page = client.get("/settings/integrations")
    assert "On-call" in page.text
    assert VALID_URL not in page.text
    assert "http****EFGH" in page.text
    assert 'href="/settings/integrations"' in page.text

    listing = client.get("/v1/settings/integrations").json()
    assert listing[0]["provider"] == "slack"
    assert listing[0]["enabled"] is True
    assert VALID_URL not in str(listing)

    other_client, _ = _client("user-2")
    assert other_client.get("/v1/settings/integrations").json() == []


@pytest.mark.parametrize(
    "url",
    ["http://hooks.slack.com/services/T000/B000/abcd", "https://evil.example/services/T000/B000/abcd"],
)
def test_invalid_slack_url_is_rejected_without_saving(url):
    client, store = _client()

    response = client.post(
        "/settings/integrations",
        data={"display_name": "Slack", "webhook_url": url, "enabled": "true"},
    )

    assert response.status_code == 400
    assert "Webhook URL" in response.text
    assert store.integrations == {}


def test_disabled_integration_is_saved_but_not_used(monkeypatch):
    client, store = _client()
    saved = FakeIntegration("user-1", "slack", "Slack", VALID_URL, False)
    store.integrations[("user-1", "slack")] = saved

    page = client.get("/settings/integrations")
    assert "Not enabled" in page.text

    class FakePoster:
        def __init__(self, webhook_url):
            self.webhook_url = webhook_url

        async def post_text(self, message):
            return True

    monkeypatch.setattr("agent_server.api.settings.SlackPoster", FakePoster)
    response = client.post("/settings/integrations/slack/test", follow_redirects=False)

    assert response.status_code == 400
    assert "Save and enable" in response.text


def test_test_message_posts_to_saved_webhook(monkeypatch):
    client, store = _client()
    store.integrations[("user-1", "slack")] = FakeIntegration("user-1", "slack", "On-call", VALID_URL, True)
    calls = []

    class FakePoster:
        def __init__(self, webhook_url):
            self.webhook_url = webhook_url

        async def post_text(self, message):
            calls.append((self.webhook_url, message))
            return True

    monkeypatch.setattr("agent_server.api.settings.SlackPoster", FakePoster)

    response = client.post("/settings/integrations/slack/test")

    assert response.status_code == 200
    assert "Test message delivered" in response.text
    assert calls[0][0] == VALID_URL
    assert "On-call" in calls[0][1]
    assert "READ-ONLY" in calls[0][1]


def test_test_briefing_is_redacted_and_bounded():
    assert "Slack" in build_test_briefing("Slack")
    assert len(build_test_briefing("Slack")) < 40_000


def test_delete_integration_is_owner_scoped():
    client, store = _client()
    store.integrations[("user-1", "slack")] = FakeIntegration("user-1", "slack", "Slack", VALID_URL, True)
    store.integrations[("user-2", "slack")] = FakeIntegration("user-2", "slack", "Slack", VALID_URL, True)

    response = client.post("/settings/integrations/slack/delete", follow_redirects=False)

    assert response.status_code == 303
    assert ("user-1", "slack") not in store.integrations
    assert ("user-2", "slack") in store.integrations


def test_json_endpoint_rejects_invalid_url():
    client, _ = _client()

    response = client.post(
        "/v1/settings/integrations",
        json={"display_name": "Slack", "webhook_url": "https://evil.example/services/x/y/z", "enabled": True},
    )

    assert response.status_code == 422
