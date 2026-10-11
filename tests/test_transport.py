import pytest
from fastapi.testclient import TestClient

from server_agent import AgentResponse, SessionContext, ToolRequest
from transport import create_app


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
    assert response.json()["token_type"] == "bearer"


def test_websocket_rejects_unauthorized_client():
    client = TestClient(create_app(auth_token="secret", agent_factory=FakeAgent))
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_websocket_correlates_tool_result_and_streams_final_message():
    client = TestClient(create_app(auth_token="secret", agent_factory=FakeAgent))
    with client.websocket_connect("/ws", headers={"Authorization": "Bearer secret"}) as socket:
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
