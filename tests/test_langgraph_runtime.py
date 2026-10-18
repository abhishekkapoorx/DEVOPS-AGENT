from types import SimpleNamespace

import pytest

from agent_core import AgentRequest
from agent_server.langgraph_runtime import LangGraphRuntime


class FakeAgent:
    def __init__(self):
        self.kwargs = None

    async def arun(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(message="answer", requests=())


@pytest.mark.asyncio
async def test_runtime_restores_persisted_conversation_history():
    agent = FakeAgent()
    runtime = LangGraphRuntime(agent=agent)
    request = AgentRequest(
        user_id="user-1",
        conversation_id="conversation-1",
        run_id="run-1",
        message="current turn",
        history=(
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
            {"role": "system", "content": "system context"},
        ),
    )

    response = await runtime.run(request)

    assert response.message == "answer"
    assert [type(item).__name__ for item in agent.kwargs["history"]] == [
        "HumanMessage",
        "AIMessage",
        "SystemMessage",
    ]


@pytest.mark.asyncio
async def test_runtime_rejects_malformed_persisted_history():
    runtime = LangGraphRuntime(agent=FakeAgent())
    request = AgentRequest(
        user_id="user-1",
        conversation_id="conversation-1",
        run_id="run-1",
        message="current turn",
        history=({"role": "unsupported", "content": "bad"},),
    )

    with pytest.raises(ValueError, match="Unsupported conversation history role"):
        await runtime.run(request)


@pytest.mark.asyncio
async def test_runtime_preserves_tool_call_ids_and_reintroduces_structured_results():
    from types import SimpleNamespace
    from agent_server.server_agent import ToolRequest

    class ToolCallingAgent:
        async def arun(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                message="done",
                requests=(ToolRequest(tool="git", action="status", arguments={}, call_id="call-42"),),
            )

    agent = ToolCallingAgent()
    runtime = LangGraphRuntime(agent=agent)
    request = AgentRequest(
        user_id="user-1",
        conversation_id="conversation-1",
        run_id="run-1",
        message="status",
        tool_results=({"call_id": "call-previous", "status": "succeeded", "output": {"status": "clean"}},),
    )

    result = await runtime.run(request)

    assert result.tool_calls[0].call_id == "call-42"
    assert agent.kwargs["tool_results"][0]["call_id"] == "call-previous"


@pytest.mark.asyncio
async def test_runtime_does_not_replay_database_history_when_checkpoint_exists():
    class Checkpointer:
        async def aget_tuple(self, config):
            assert config["configurable"]["thread_id"]
            return object()

    class CheckpointedAgent(FakeAgent):
        checkpointer = Checkpointer()

    agent = CheckpointedAgent()
    runtime = LangGraphRuntime(agent=agent)
    request = AgentRequest(
        user_id="user-1",
        conversation_id="conversation-1",
        run_id="run-2",
        message="second turn",
        history=({"role": "user", "content": "first turn"},),
    )

    await runtime.run(request)

    assert agent.kwargs["history"] == ()


@pytest.mark.asyncio
async def test_runtime_reconstructs_history_when_no_checkpoint_exists():
    class Checkpointer:
        async def aget_tuple(self, config):
            return None

    class CheckpointedAgent(FakeAgent):
        checkpointer = Checkpointer()

    agent = CheckpointedAgent()
    await LangGraphRuntime(agent=agent).run(
        AgentRequest(
            user_id="user-1",
            conversation_id="conversation-1",
            run_id="run-1",
            message="current",
            history=({"role": "user", "content": "earlier"},),
        )
    )
    assert [item.content for item in agent.kwargs["history"]] == ["earlier"]
