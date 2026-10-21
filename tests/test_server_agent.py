import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

from agent_server.server_agent import (
    AgentResponse,
    SessionContext,
    ToolRequest,
    registered_request_tools,
)


def test_tool_request_is_strictly_validated():
    request = ToolRequest(tool="cloud", action="provision", arguments={"provider": "aws"})

    assert request.model_dump() == {
        "tool": "cloud",
        "action": "provision",
        "version": "1.0.0",
        "arguments": {"provider": "aws"},
    }
    with pytest.raises(ValidationError):
        ToolRequest(tool="cloud", action="Run shell", arguments={})


def test_registered_tools_expose_only_authorized_catalog_entries_to_the_model():
    tools = registered_request_tools(
        (
            {
                "name": "git.status",
                "version": "2.0.0",
                "description": "Read git status for an allowed repository.",
                "input_schema": {
                    "type": "object",
                    "properties": {"repository_id": {"type": "string"}},
                    "required": ["repository_id"],
                },
            },
            {"name": "unreviewed.execute", "version": "1", "description": "unreviewed"},
            {"name": "invalid name", "version": "1", "description": "invalid"},
        )
    )

    assert len(tools) == 1
    request = json.loads(tools[0].invoke({"arguments": {"repository_id": "workspace"}}))
    assert request == {
        "tool": "git",
        "action": "status",
        "version": "2.0.0",
        "arguments": {"repository_id": "workspace"},
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
    assert response.requests == (
        ToolRequest(tool="docker", action="build", arguments={}, call_id="1"),
    )


def test_unknown_tool_actions_fail_closed():
    with pytest.raises(ValueError, match="Unknown or unauthorized"):
        ToolRequest(tool="docker", action="execute_shell", arguments={})
