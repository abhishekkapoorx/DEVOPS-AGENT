import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

from server_agent import AgentResponse, REQUEST_TOOLS, SessionContext, ToolRequest


def test_tool_request_is_strictly_validated():
    request = ToolRequest(tool="cloud", action="provision", arguments={"provider": "aws"})

    assert request.model_dump() == {
        "tool": "cloud",
        "action": "provision",
        "arguments": {"provider": "aws"},
    }
    with pytest.raises(ValidationError):
        ToolRequest(tool="cloud", action="Run shell", arguments={})


def test_request_tool_returns_intent_without_executing_it():
    result = REQUEST_TOOLS[0].invoke(
        {"action": "provision", "arguments": {"provider": "aws", "resource": "s3"}}
    )

    assert json.loads(result) == {
        "tool": "cloud",
        "action": "provision",
        "arguments": {"provider": "aws", "resource": "s3"},
    }


def test_agent_response_discards_malformed_tool_messages():
    response = AgentResponse.from_result(
        {
            "messages": [
                AIMessage(content="Planning complete"),
                ToolMessage(content='{"tool":"docker","action":"build","arguments":{}}', tool_call_id="1"),
                ToolMessage(content="not json", tool_call_id="2"),
            ]
        },
        context=SessionContext(user_id="u-1", session_id="s-1"),
    )

    assert response.message == "Planning complete"
    assert response.requests == (ToolRequest(tool="docker", action="build", arguments={}),)
