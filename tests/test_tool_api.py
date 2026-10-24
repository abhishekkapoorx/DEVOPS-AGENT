from fastapi.testclient import TestClient

from agent_server.api.app import create_app
from agent_server.auth import issue_access_token
from agent_server.auth_sessions import AuthSessionService
from agent_server.persistence.memory import InMemoryConversationRepository


class RecordingBroker:
    def __init__(self, *, accepts_result=True):
        self.accepts_result = accepts_result
        self.submitted = None

    def submit_result(self, user_id, call_id, result):
        self.submitted = (user_id, call_id, result)
        return self.accepts_result


def _client(broker):
    secret = "local-tool-result-test-secret-at-least-32-chars"
    repository = InMemoryConversationRepository()
    app = create_app(
        runtime=object(),
        conversations=repository,
        runs=repository,
        auth_service=AuthSessionService(
            repository=object(), approval_provider=object(), access_token_secret=secret
        ),
        run_worker=object(),
        local_tool_broker=broker,
    )
    token = issue_access_token(secret, "user-1")
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def test_local_tool_result_is_parsed_from_json_body():
    broker = RecordingBroker()
    client = _client(broker)
    payload = {
        "exit_code": 0,
        "stdout": "workspace files",
        "stderr": "",
        "duration_ms": 12.5,
    }

    response = client.post("/v1/local-tools/call-1/result", json=payload)

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "accepted"}
    assert broker.submitted == ("user-1", "call-1", payload)


def test_local_tool_result_reports_when_the_call_is_no_longer_pending():
    client = _client(RecordingBroker(accepts_result=False))

    response = client.post(
        "/v1/local-tools/call-1/result",
        json={"exit_code": 1, "stdout": "", "stderr": "failed", "duration_ms": 3},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Tool request is no longer pending"
