import io
import json
import urllib.error

from agent_cli.rest_client import RestAgentClient


class FakeResponse:
    def __init__(self, payload=b"", *, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self._stream = io.BytesIO(payload)

    def read(self, size=-1):
        return self._stream.read(size)

    def readline(self):
        return self._stream.readline()

    def close(self):
        pass


def _json_response(value, status=200):
    return FakeResponse(json.dumps(value).encode(), status=status)


def test_rest_client_creates_conversation_submits_idempotently_and_replays_sse():
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        path = request.full_url.split("example.test", 1)[1]
        if request.method == "POST" and path == "/v1/conversations":
            return _json_response({"id": "conversation-1", "title": "hello"}, 201)
        if request.method == "POST" and path.endswith("/messages"):
            assert request.get_header("Idempotency-key") == "stable-key"
            assert json.loads(request.data) == {"content": "hello"}
            return _json_response(
                {"run_id": "run-1", "message_id": "message-1", "status": "pending", "message": "", "tool_calls": []},
                202,
            )
        if path.endswith("/events/stream?after=0"):
            return FakeResponse(
                b"id: 1\nevent: created\ndata: {\"state\":\"pending\"}\n\n"
                b"id: 2\nevent: running\ndata: {\"state\":\"running\"}\n\n"
                b"id: 3\nevent: completed\ndata: {\"state\":\"completed\",\"message\":\"done\"}\n\n",
                headers={"Content-Type": "text/event-stream"},
            )
        if request.method == "GET" and path == "/v1/runs/run-1":
            return _json_response(
                {"run_id": "run-1", "message_id": "message-1", "status": "completed", "message": "done", "tool_calls": []}
            )
        raise AssertionError(f"unexpected request {request.method} {path}")

    received = []
    client = RestAgentClient(
        "https://example.test",
        access_token=lambda: "access",
        refresh_access_token=lambda: None,
        opener=opener,
    )
    result = client.ask("hello", idempotency_key="stable-key", on_event=received.append)

    assert result["message"] == "done"
    assert [event["type"] for event in received] == ["created", "running", "agent_message"]
    assert received[-1] == {"type": "agent_message", "message": "done", "final": True}
    assert len(requests) == 4


def test_rest_client_refreshes_access_token_after_401():
    attempts = 0

    def opener(request, *, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise urllib.error.HTTPError(
                request.full_url, 401, "expired", {}, io.BytesIO(b'{"detail":"expired"}')
            )
        path = request.full_url.split("example.test", 1)[1]
        if request.method == "POST" and path == "/v1/conversations":
            return _json_response({"id": "conversation-1", "title": "test"}, 201)
        if request.method == "POST" and path.endswith("/messages"):
            return _json_response(
                {"run_id": "run-1", "message_id": "message-1", "status": "pending", "message": "", "tool_calls": []},
                202,
            )
        if path.endswith("/events/stream?after=0"):
            return FakeResponse(
                b"id: 1\nevent: completed\ndata: {\"state\":\"completed\",\"message\":\"done\"}\n\n"
            )
        if request.method == "GET" and path == "/v1/runs/run-1":
            return _json_response(
                {"run_id": "run-1", "message_id": "message-1", "status": "completed", "message": "done", "tool_calls": []}
            )
        raise AssertionError(f"unexpected request {request.method} {path}")

    refreshed = []
    client = RestAgentClient(
        "https://example.test",
        access_token=lambda: "old-access",
        refresh_access_token=lambda: refreshed.append("new-access") or "new-access",
        opener=opener,
    )

    result = client.ask("test")

    assert result["message"] == "done"
    assert refreshed == ["new-access"]


def test_sse_reconnect_cursor_advances_only_after_complete_event():
    stream_requests = []
    state_requests = 0

    def opener(request, *, timeout):
        nonlocal state_requests
        path = request.full_url.split("example.test", 1)[1]
        if request.method == "POST" and path == "/v1/conversations":
            return _json_response({"id": "conversation-1"}, 201)
        if request.method == "POST" and path.endswith("/messages"):
            return _json_response({"run_id": "run-1", "status": "pending"}, 202)
        if "/events/stream?" in path:
            stream_requests.append(path)
            if len(stream_requests) == 1:
                return FakeResponse(b'id: 7\nevent: completed\ndata: {"sequence":7')
            return FakeResponse(
                b'id: 7\nevent: completed\ndata: {"sequence":7,"message":"done"}\n\n'
            )
        if request.method == "GET" and path == "/v1/runs/run-1":
            state_requests += 1
            status = "pending" if state_requests == 1 else "completed"
            return _json_response({"status": status, "message": "done"})
        raise AssertionError(f"unexpected request {request.method} {path}")

    client = RestAgentClient(
        "https://example.test",
        access_token=lambda: "access",
        refresh_access_token=lambda: None,
        opener=opener,
        sleep=lambda _: None,
    )
    assert client.ask("hello")["message"] == "done"
    assert stream_requests == [
        "/v1/runs/run-1/events/stream?after=0",
        "/v1/runs/run-1/events/stream?after=0",
    ]
