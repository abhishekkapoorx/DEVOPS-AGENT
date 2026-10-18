import json

from fastapi.testclient import TestClient

from agent_core.runtime import AgentResponse
from agent_server.auth import issue_access_token
from agent_server.auth_sessions import AuthSessionService
from agent_server.api.app import create_app
from agent_server.persistence.memory import InMemoryConversationRepository


class FakeRuntime:
    def __init__(self):
        self.calls = 0
        self.error = None
        self.last_run_id = None

    async def run(self, request):
        self.calls += 1
        self.last_run_id = request.run_id
        if self.error:
            raise self.error
        return AgentResponse(message=f"answer {self.calls}")


def _client():
    runtime = FakeRuntime()
    repository = InMemoryConversationRepository()
    secret = "test-access-token-secret"
    app = create_app(
        runtime=runtime,
        conversations=repository,
        runs=repository,
        auth_service=AuthSessionService(
            repository=object(), approval_provider=object(), access_token_secret=secret
        ),
    )
    token = issue_access_token(secret, "user-1")
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    conversation = client.post("/v1/conversations", json={"title": "test"}).json()
    return client, runtime, conversation["id"]


def test_message_retry_returns_same_result_without_running_agent_twice():
    client, runtime, conversation_id = _client()
    url = f"/v1/conversations/{conversation_id}/messages"
    headers = {"Idempotency-Key": "request-123"}

    first = client.post(url, headers=headers, json={"content": "hello"})
    retry = client.post(url, headers=headers, json={"content": "hello"})

    assert first.status_code == 202
    assert retry.status_code == 200
    assert first.json()["run_id"] == retry.json()["run_id"]
    assert first.json()["message_id"] == retry.json()["message_id"]
    assert first.json()["status"] == "pending"
    assert first.json()["message_id"]
    assert retry.json()["status"] == "completed"
    assert runtime.calls == 1
    assert len(client.get(f"/v1/conversations/{conversation_id}/messages").json()) == 2


def test_reusing_idempotency_key_for_different_content_is_rejected():
    client, runtime, conversation_id = _client()
    url = f"/v1/conversations/{conversation_id}/messages"
    headers = {"Idempotency-Key": "request-123"}
    client.post(url, headers=headers, json={"content": "hello"})

    response = client.post(url, headers=headers, json={"content": "different"})

    assert response.status_code == 409
    assert runtime.calls == 1


def test_message_requires_an_idempotency_key():
    client, runtime, conversation_id = _client()

    response = client.post(
        f"/v1/conversations/{conversation_id}/messages", json={"content": "hello"}
    )

    assert response.status_code == 422
    assert runtime.calls == 0


def test_completed_run_and_events_can_be_replayed():
    client, _, conversation_id = _client()
    response = client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Idempotency-Key": "request-456"},
        json={"content": "hello"},
    )
    run_id = response.json()["run_id"]

    restored = client.get(f"/v1/runs/{run_id}")
    events = client.get(f"/v1/runs/{run_id}/events")
    replay = client.get(f"/v1/runs/{run_id}/events?after=1")

    assert restored.status_code == 200
    assert restored.json()["status"] == "completed"
    assert [event["type"] for event in events.json()] == ["created", "running", "completed"]
    assert [event["sequence"] for event in replay.json()] == [2, 3]


def test_runtime_failure_is_recorded_as_a_failed_run():
    client, runtime, conversation_id = _client()
    runtime.error = RuntimeError("private provider detail")

    response = client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Idempotency-Key": "request-failure"},
        json={"content": "hello"},
    )

    assert response.status_code == 202
    persisted = client.get(f"/v1/runs/{runtime.last_run_id}")
    assert persisted.status_code == 200
    assert persisted.json()["status"] == "failed"
    assert persisted.json()["error"] == "Agent runtime failed"
    assert client.get(
        f"/v1/runs/{runtime.last_run_id}/events"
    ).json()[-1]["type"] == "failed"
    assert runtime.calls == 1


def test_readiness_requires_persistence_health():
    client, _, _ = _client()

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_api_mounts_authentication_routes_and_returns_verified_identity():
    client, _, _ = _client()

    response = client.get("/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-1"}


def test_run_events_are_available_as_sse_for_reconnect():
    client, _, conversation_id = _client()
    turn = client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Idempotency-Key": "request-stream"},
        json={"content": "hello"},
    ).json()

    response = client.get(f"/v1/runs/{turn['run_id']}/events/stream?after=1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 2\nevent: running" in response.text
    assert "id: 3\nevent: completed" in response.text
    data_line = next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
    assert json.loads(data_line)["state"] == "running"


def test_run_cancel_endpoint_does_not_rewrite_a_completed_run():
    client, _, conversation_id = _client()
    turn = client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Idempotency-Key": "cancel-completed"},
        json={"content": "hello"},
    ).json()

    response = client.delete(f"/v1/runs/{turn['run_id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_run_cancel_endpoint_hides_runs_owned_by_another_user():
    client, _, conversation_id = _client()
    turn = client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers={"Idempotency-Key": "cancel-owner"},
        json={"content": "hello"},
    ).json()
    secret = "test-access-token-secret"
    other = TestClient(
        client.app,
        headers={"Authorization": f"Bearer {issue_access_token(secret, 'other-user')}"},
    )

    response = other.delete(f"/v1/runs/{turn['run_id']}")

    assert response.status_code == 404
