import asyncio
import io
import json

import pytest

from agent_core.tools import ToolExecutionContext
from agent_server.tool_client import RestToolServiceClient


class Response:
    def __init__(self, body):
        self.body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body.read(size)


def test_rest_tool_service_client_sends_correlation_and_idempotency_context():
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        assert timeout == 5
        return Response(
            json.dumps(
                {
                    "call_id": "call-1",
                    "name": "git.status",
                    "status": "succeeded",
                    "output": {"status": "clean"},
                    "error": None,
                    "duration_ms": 5,
                }
            ).encode()
        )

    client = RestToolServiceClient(
        "https://tools.example", access_token=lambda _context: "signed-token", opener=opener, timeout=5
    )
    context = ToolExecutionContext(
        user_id="user-1",
        run_id="run-1",
        call_id="call-1",
        scopes=frozenset({"git:read"}),
        correlation_id="corr-1",
        idempotency_key="idem-1",
        traceparent="00-abc-def-01",
    )

    result = asyncio.run(
        client.execute(name="git.status", version="1.0.0", arguments={}, context=context)
    )

    assert result.status == "succeeded"
    assert result.output == {"status": "clean"}
    assert requests[0].get_header("Authorization") == "Bearer signed-token"
    assert requests[0].get_header("Idempotency-key") == "idem-1"
    assert requests[0].get_header("X-correlation-id") == "corr-1"
    assert requests[0].get_header("Traceparent") == "00-abc-def-01"


def test_tool_client_requires_explicit_permission_for_non_loopback_http():
    access_token = lambda _context: "token"

    with pytest.raises(ValueError, match="HTTPS"):
        RestToolServiceClient("http://tool-service:8001", access_token=access_token)

    client = RestToolServiceClient(
        "http://tool-service:8001",
        access_token=access_token,
        allow_insecure_http=True,
    )

    assert client.base_url == "http://tool-service:8001"
