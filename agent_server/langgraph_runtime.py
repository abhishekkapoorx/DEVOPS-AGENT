"""LangGraph implementation of the framework-independent Agent Runtime."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent_core import AgentRequest, AgentResponse, AgentToolCall

from .server_agent import ServerAgent


class LangGraphRuntime:
    """Adapt the current request-producing LangGraph agent to AgentRuntime."""

    def __init__(self, agent: ServerAgent | None = None, *, model: Any | None = None):
        self._agent = agent or ServerAgent(model=model)

    async def run(self, request: AgentRequest) -> AgentResponse:
        """Run a turn and translate LangGraph output to domain contracts."""

        response = await self._agent.arun(
            user_id=request.user_id,
            session_id=request.conversation_id,
            message=request.message,
        )
        calls = tuple(
            AgentToolCall(
                call_id=str(uuid4()),
                name=f"{tool_request.tool}.{tool_request.action}",
                arguments=tool_request.arguments,
            )
            for tool_request in response.requests
        )
        return AgentResponse(message=response.message, tool_calls=calls)


__all__ = ["LangGraphRuntime"]
