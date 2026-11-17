import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_core.runtime import AgentResponse
from agent_server.alertmanager import NormalizedAlert
from agent_server.api.app import create_app
from agent_server.auth_sessions import AuthSessionService
from agent_server.persistence.memory import InMemoryConversationRepository


SCENARIO_FIXTURES = sorted(
    Path("incident-investigation-lab/scenarios").glob("*/alert_fixture*.json")
)


class FakeRuntime:
    async def run(self, request):
        return AgentResponse(message="unused")


class FakeSession:
    def __init__(self):
        self.rows = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        self.commits += 1


def _client(*, token=None, ingest=None):
    session = FakeSession()

    def sessions():
        return session

    app = create_app(
        runtime=FakeRuntime(),
        conversations=InMemoryConversationRepository(),
        runs=InMemoryConversationRepository(),
        auth_service=AuthSessionService(
            repository=object(), approval_provider=object(), access_token_secret="test-secret"
        ),
        database_sessions=sessions,
        webhook_token=token,
        webhook_ingest_alerts=ingest,
    )
    client = TestClient(app)
    client.app.state.webhook_test_session = session
    return client, session


@pytest.mark.parametrize("fixture_path", SCENARIO_FIXTURES)
def test_alertmanager_fixture_is_accepted(fixture_path):
    client, session = _client()

    response = client.post("/webhook/alertmanager", json=json.loads(fixture_path.read_text()))

    assert response.status_code == 202
    assert response.json() == {"received": 1, "accepted": 1, "skipped": 0}
    assert session.commits == 1
    assert len(session.rows) == 1
    assert session.rows[0].body["version"] == "4"


def test_malformed_alert_is_skipped_without_discarding_valid_alert():
    client, _ = _client()
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())
    payload["alerts"].append({"status": "firing", "labels": {}})

    response = client.post("/webhook/alertmanager", json=payload)

    assert response.status_code == 202
    assert response.json() == {"received": 2, "accepted": 1, "skipped": 1}


def test_non_object_alert_is_skipped_without_invalidating_payload():
    client, _ = _client()
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())
    payload["alerts"].append("not-an-alert-object")

    response = client.post("/webhook/alertmanager", json=payload)

    assert response.status_code == 202
    assert response.json() == {"received": 2, "accepted": 1, "skipped": 1}


def test_wrong_version_is_rejected():
    client, session = _client()
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())
    payload["version"] = "3"

    response = client.post("/webhook/alertmanager", json=payload)

    assert response.status_code == 422
    assert "expected 4" in response.json()["detail"]
    assert session.rows == []


def test_oversized_body_is_rejected():
    client, _ = _client()
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())
    payload["commonAnnotations"]["description"] = "x" * (1024 * 1024)

    response = client.post("/webhook/alertmanager", json=payload)

    assert response.status_code == 413


@pytest.mark.parametrize("authorization", [None, "Bearer wrong"])
def test_configured_webhook_token_rejects_missing_or_incorrect_credentials(authorization):
    client, _ = _client(token="expected")
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())
    headers = {} if authorization is None else {"Authorization": authorization}

    response = client.post("/webhook/alertmanager", json=payload, headers=headers)

    assert response.status_code == 401


def test_configured_webhook_token_accepts_bearer_credentials():
    client, _ = _client(token="expected")
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())

    response = client.post(
        "/webhook/alertmanager",
        json=payload,
        headers={"Authorization": "Bearer expected"},
    )

    assert response.status_code == 202


def test_environment_webhook_token_is_enforced(monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", "from-environment")
    client, _ = _client()
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())

    response = client.post("/webhook/alertmanager", json=payload)

    assert response.status_code == 401


def test_endpoint_hands_normalized_alerts_to_ingestion_seam():
    received = []

    async def ingest(session, alerts):
        received.extend(alerts)
        return []

    client, _ = _client(ingest=ingest)
    payload = json.loads(SCENARIO_FIXTURES[0].read_text())

    response = client.post("/webhook/alertmanager", json=payload)

    assert response.status_code == 202
    assert len(received) == 1
    assert isinstance(received[0], NormalizedAlert)
    assert received[0].alertname == "KubePodCrashLooping"
