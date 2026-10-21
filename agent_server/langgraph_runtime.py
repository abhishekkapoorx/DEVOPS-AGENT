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

        return await self._run(request, on_event=None)

    async def run_stream(self, request: AgentRequest, *, on_event) -> AgentResponse:
        """Stream user-visible model text while retaining the final structured response."""

        return await self._run(request, on_event=on_event)

    async def _run(self, request: AgentRequest, *, on_event) -> AgentResponse:

        thread_id = _thread_id(request.user_id, request.conversation_id)
        history = tuple(_history_message(item) for item in request.history)
        checkpointer = getattr(self._agent, "checkpointer", None)
        if checkpointer is not None:
            checkpoint = await checkpointer.aget_tuple(
                {"configurable": {"thread_id": thread_id}}
            )
            if checkpoint is not None:
                # The stable thread already owns its message history. Replaying the
                # database history would append every prior message a second time.
                history = ()
        arguments = {
            "user_id": request.user_id,
            "session_id": thread_id,
            "message": request.message,
            "history": history,
            "tool_results": request.tool_results,
            "run_id": request.run_id,
            "correlation_id": request.correlation_id,
            "traceparent": request.traceparent,
            "available_tools": request.available_tools,
        }
        if on_event is None:
            response = await self._agent.arun(**arguments)
        else:
            response = await self._agent.arun_stream(**arguments, on_event=on_event)
        calls = tuple(
            AgentToolCall(
                call_id=tool_request.call_id or str(uuid4()),
                name=f"{tool_request.tool}.{tool_request.action}",
                version=tool_request.version,
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

    # AsyncPostgresSaver uses psycopg's URL syntax, while the SQLAlchemy
    # repository factory accepts the driver-qualified asyncpg form.
    checkpoint_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    async with AsyncPostgresSaver.from_conn_string(checkpoint_url) as checkpointer:
        await checkpointer.setup()
        yield LangGraphRuntime(model=model, checkpointer=checkpointer)


__all__ = ["LangGraphRuntime", "postgres_runtime"]
