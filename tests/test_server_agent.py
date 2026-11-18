import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from pydantic import ValidationError

from agent_server.server_agent import (
    AgentResponse,
    ServerAgent,
    SessionContext,
    ToolRequest,
    registered_request_tools,
)
from agent_core import AgentRequest
from agent_server.langgraph_runtime import LangGraphRuntime


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


def test_registered_tools_expose_only_supported_local_tools_to_the_model():
    tools = registered_request_tools(
        (
            {
                "name": "git.command",
                "version": "1.0.0",
                "description": "Run a local Git command.",
            },
            {"name": "git.command", "version": "2.0.0", "description": "unsupported version"},
            {"name": "unreviewed.execute", "version": "1", "description": "unreviewed"},
            {"name": "invalid name", "version": "1", "description": "invalid"},
        )
    )

    assert len(tools) == 1
    assert tools[0].name == "git_command"
    assert set(tools[0].args) == {"argv", "cwd"}
    assert tools[0].description == "Run a local Git command."


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


def test_unknown_local_tools_are_not_registered_for_the_agent():
    tools = registered_request_tools(
        ({"name": "docker.execute_shell", "version": "1.0.0", "description": "unsupported"},)
    )

    assert tools == ()


@pytest.mark.asyncio
async def test_agent_stream_records_nested_graph_steps_and_subagent_lifecycle():
    class Graph:
        async def astream(self, *_args, **kwargs):
            assert kwargs["subgraphs"] is True
            yield ("security_agent:task-1",), ("updates", {"inspect": {"finding_count": 2}})
            yield ("security_agent:task-1",), (
                "messages", (AIMessageChunk(content="Found two issues"), {})
            )
            yield "values", {"messages": [AIMessage(content="Analysis complete")]}

    agent = ServerAgent()
    agent._get_graph = lambda _tools: Graph()
    events = []

    async def receive(event):
        events.append(event)

    await LangGraphRuntime(agent=agent).run_stream(
        AgentRequest(
            user_id="user-1",
            conversation_id="conversation-1",
            run_id="run-1",
            message="check security",
        ),
        on_event=receive,
    )

    assert [event["type"] for event in events] == [
        "subagent_started", "subagent_update", "agent_delta", "subagent_completed"
    ]
    assert events[1]["updated_keys"] == ["finding_count"]
    assert events[1]["result"] == {"finding_count": 2}
    assert events[2]["namespace"] == ["security_agent:task-1"]
