"""LangGraph implementation of the framework-independent Agent Runtime."""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from agent_core import AgentRequest, AgentResponse, AgentToolCall
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .server_agent import ServerAgent


class LangGraphRuntime:
    """Adapt the current request-producing LangGraph agent to AgentRuntime."""

    def __init__(
        self,
        agent: ServerAgent | None = None,
        *,
        model: Any | None = None,
        checkpointer: Any | None = None,
    ):
        self._agent = agent or ServerAgent(model=model, checkpointer=checkpointer)

    async def run(self, request: AgentRequest) -> AgentResponse:
        """Run a turn and translate LangGraph output to domain contracts."""

        response = await self._agent.arun(
            user_id=request.user_id,
            session_id=_thread_id(request.user_id, request.conversation_id),
            message=request.message,
            history=tuple(_history_message(item) for item in request.history),
            run_id=request.run_id,
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


def _history_message(item: Any) -> BaseMessage:
    """Translate persisted role/content records into framework messages."""
    if not isinstance(item, dict) or not isinstance(item.get("content"), str):
        raise ValueError("Agent history entries must contain a role and string content")
    role = item.get("role")
    content = item["content"]
    if role == "user":
        return HumanMessage(content=content)
    if role == "assistant":
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    if role == "tool":
        tool_call_id = item.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            raise ValueError("Persisted tool history requires a tool_call_id")
        return ToolMessage(content=content, tool_call_id=tool_call_id)
    raise ValueError(f"Unsupported conversation history role: {role!r}")


def _thread_id(user_id: str, conversation_id: str) -> str:
    """Derive an opaque, stable, user-scoped checkpoint thread identifier."""

    value = f"{user_id}\0{conversation_id}".encode()
    return hashlib.sha256(value).hexdigest()


@asynccontextmanager
async def postgres_runtime(database_url: str, *, model: Any | None = None):
    """Open a LangGraph runtime whose checkpoint state is stored in Postgres."""

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
        await checkpointer.setup()
        yield LangGraphRuntime(model=model, checkpointer=checkpointer)


__all__ = ["LangGraphRuntime", "postgres_runtime"]
