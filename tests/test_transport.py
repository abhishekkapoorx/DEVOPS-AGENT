import json
import pytest
from fastapi.testclient import TestClient

from agent_cli.websocket_client import AgentWebSocketClient
from agent_server.server_agent import AgentResponse, SessionContext, ToolRequest
from agent_server.transport import create_app


class FakeAgent:
    def __init__(self):
        self.calls = 0

    async def arun(self, *, user_id, session_id, message, history=None):
        self.calls += 1
        if self.calls == 1:
            return AgentResponse(
                context=SessionContext(user_id=user_id, session_id=session_id),
                message="I need a local check.",
                requests=(ToolRequest(tool="git", action="status", arguments={}),),
            )
        return AgentResponse(
            context=SessionContext(user_id=user_id, session_id=session_id),
            message="The check completed.",
            requests=(),
        )


def test_health_and_authentication_endpoints():
    client = TestClient(create_app(auth_token="secret", agent_factory=FakeAgent))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/auth/token", json={"token": "wrong"}).status_code == 401
    response = client.post("/auth/token", json={"token": "secret"})
    assert response.json()["authenticated"] is True
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"].startswith("da1.")


def test_websocket_rejects_unauthorized_client():
    client = TestClient(create_app(auth_token="secret", agent_factory=FakeAgent))
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_websocket_correlates_tool_result_and_streams_final_message():
    client = TestClient(create_app(auth_token="secret", agent_factory=FakeAgent))
    token = client.post("/auth/token", json={"token": "secret", "user_id": "u-1"}).json()["access_token"]
    with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}) as socket:
        socket.send_json({"type": "user_message", "message": "Check git", "user_id": "u-1"})
        first = socket.receive_json()
        request = socket.receive_json()
        assert first == {"type": "agent_message", "message": "I need a local check.", "final": False}
        assert request["type"] == "tool_request"
        socket.send_json({
            "type": "tool_result",
            "request_id": request["request_id"],
            "result": {"exit_code": 0, "stdout": "clean"},
        })
        assert socket.receive_json() == {
            "type": "agent_message", "message": "The check completed.", "final": True
        }


def test_websocket_rejects_malformed_tool_result_without_closing_session():
    client = TestClient(create_app(auth_token="secret", agent_factory=FakeAgent))
    token = client.post("/auth/token", json={"token": "secret", "user_id": "cli-user"}).json()["access_token"]
    with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}) as socket:
        socket.send_json({"type": "user_message", "message": "Check git"})
        socket.receive_json()
        request = socket.receive_json()
        socket.send_json({"type": "tool_result", "request_id": request["request_id"]})
        assert socket.receive_json() == {"type": "error", "message": "Malformed tool result"}


def test_client_requires_tls():
    with pytest.raises(ValueError, match="wss://"):
        AgentWebSocketClient("ws://localhost/ws", "secret")


class _FakeConnection:
    def __init__(self):
        self.sent = []
        self.incoming = iter(
            [
                {"type": "agent_message", "message": "Inspecting resources", "final": False},
                {
                    "type": "tool_request",
                    "request_id": "request-1",
                    "tool": "cloud",
                    "action": "list",
                    "arguments": {"provider": "gcp", "resource": "instances"},
                },
                {
                    "type": "tool_request",
                    "request_id": "request-2",
                    "tool": "git",
                    "action": "status",
                    "arguments": {"args": ["--short"]},
                },
                {"type": "agent_message", "message": "Investigation complete", "final": True},
            ]
        )

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        return json.dumps(next(self.incoming))

    async def close(self):
        return None


class _RecordingExecutor:
    def __init__(self):
        self.requests = []

    def execute(self, request, *, request_id):
        self.requests.append((request, request_id))
        from agent_cli.executor import ExecutionResult

        return ExecutionResult(request.tool, request.args, 0, "ok", "", 1.0)


class _MalformedArgumentsConnection(_FakeConnection):
    def __init__(self):
        super().__init__()
        self.incoming = iter(
            [
                {
                    "type": "tool_request",
                    "request_id": "bad-request",
                    "tool": "git",
                    "action": "status",
                    "arguments": {"args": {"unexpected": "mapping"}},
                },
                {"type": "agent_message", "message": "Recovered", "final": True},
            ]
        )


@pytest.mark.asyncio
async def test_client_executes_multiple_requests_preserves_arguments_and_streams_progress(monkeypatch):
    connection = _FakeConnection()
    executor = _RecordingExecutor()
    progress = []

    async def fake_connect(*args, **kwargs):
        return connection

    monkeypatch.setattr("agent_cli.websocket_client.connect", fake_connect)
    client = AgentWebSocketClient(
        "wss://agent.example/ws",
        "access-token",
        executor=executor,
    )

    async with client:
        await client.ask("Investigate", on_message=progress.append)

    assert [message["message"] for message in progress if message["type"] == "agent_message"] == [
        "Inspecting resources",
        "Investigation complete",
    ]
    assert [(request.tool, request.args) for request, _ in executor.requests] == [
        ("gcloud", ("list", "--resource", "instances")),
        ("git", ("status", "--short")),
    ]
    assert [message["type"] for message in connection.sent] == [
        "user_message",
        "tool_result",
        "tool_result",
    ]


@pytest.mark.asyncio
async def test_client_returns_structured_failure_for_malformed_arguments(monkeypatch):
    connection = _MalformedArgumentsConnection()

    async def fake_connect(*args, **kwargs):
        return connection

    monkeypatch.setattr("agent_cli.websocket_client.connect", fake_connect)
    client = AgentWebSocketClient("wss://agent.example/ws", "access-token")

    async with client:
        await client.ask("Recover")

    assert connection.sent[1]["type"] == "tool_result"
    assert connection.sent[1]["result"]["exit_code"] == 400
    assert "args must be a string or a sequence" in connection.sent[1]["result"]["stderr"]
