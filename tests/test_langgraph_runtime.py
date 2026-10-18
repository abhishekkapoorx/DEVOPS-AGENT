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
