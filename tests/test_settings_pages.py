from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.api.settings import create_settings_router
from agent_server.auth import issue_access_token
from agent_server.auth_sessions import AuthSessionService
from tests.test_auth_sessions import MemoryAuthRepository


class FakeSecretRepository:
    def __init__(self):
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


def _client():
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
            template_dir=__import__("pathlib").Path("agent_server/templates"),
        )
    )
    client = TestClient(app, cookies={"devops_access_token": issue_access_token("test-secret", "user-1")})
    return client, store


def test_settings_page_generates_one_time_webhook_secret():
    client, store = _client()

    response = client.post("/settings/webhook-secrets", data={"name": "kind-alertmanager"})

    assert response.status_code == 200
    assert "whsec_once" in response.text
    assert "credentials: whsec_once" in response.text
    assert 'href="/investigations"' in response.text
    assert "Workspace" in response.text
    assert response.text.count('aria-label="Primary navigation"') == 1
    assert store.webhooks[0].name == "kind-alertmanager"


def test_settings_page_offers_all_alertmanager_installation_formats():
    client, _ = _client()

    response = client.post("/settings/webhook-secrets", data={"name": "kind-alertmanager"})

    assert response.status_code == 200
    assert "Download Kustomize bundle" in response.text
    assert "Download Helm values" in response.text
    assert "Download Operator manifest" in response.text
    artifact_id = response.text.split("/settings/webhook-manifests/", 1)[1].split("/", 1)[0]

    kustomize = client.get(f"/settings/webhook-manifests/{artifact_id}/kustomize")
    helm = client.get(f"/settings/webhook-manifests/{artifact_id}/helm")
    operator = client.get(f"/settings/webhook-manifests/{artifact_id}/operator")

    assert kustomize.status_code == 200
    assert kustomize.headers["content-type"] == "application/zip"
    assert b"webhook-secret.yaml" in kustomize.content
    assert helm.status_code == 200
    assert "credentials_file:" in helm.text
    assert operator.status_code == 200
    assert "kind: AlertmanagerConfig" in operator.text


def test_settings_json_endpoint_never_lists_raw_secret():
    client, _ = _client()
    client.post("/settings/webhook-secrets", data={"name": "kind-alertmanager"})

    response = client.get("/v1/settings/webhook-secrets")

    assert response.status_code == 200
    assert "secret" not in response.json()[0]


def test_settings_page_redirects_unauthenticated_users_to_login():
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
            template_dir=__import__("pathlib").Path("agent_server/templates"),
        )
    )

    response = TestClient(app).get("/settings", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
