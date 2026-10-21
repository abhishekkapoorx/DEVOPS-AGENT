"""Server-side DevOps agent.

This module contains the cloud-facing boundary for the project. It may decide
that an operation is needed, but it never performs that operation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

from langchain.agents import create_agent
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from agent_protocol import policy_for


class SessionContext(BaseModel):
    """Immutable request context supplied by the server for one conversation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class ToolRequest(BaseModel):
    """A validated operation request for an external executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    tool: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    action: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(default="1.0.0", min_length=1, pattern=r"^[A-Za-z0-9._+-]+$")
    call_id: str | None = Field(default=None, min_length=1, exclude=True)
    arguments: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        policy_for(self.tool, self.action)


class _RegisteredToolInput(BaseModel):
    arguments: dict[str, Any] = Field(
        description="Arguments matching the registered tool's input schema."
    )


def registered_request_tools(available_tools: Sequence[Mapping[str, Any]]) -> tuple[StructuredTool, ...]:
    """Create model-facing request functions only for the authorized registry catalog."""

    tools = []
    for index, definition in enumerate(available_tools):
        name = definition.get("name")
        version = definition.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        tool_name, separator, action = name.partition(".")
        if not separator:
            continue
        try:
            policy_for(tool_name, action)
        except ValueError:
            continue
        description = str(definition.get("description") or name)
        input_schema = definition.get("input_schema")
        description += (
            " Input JSON Schema: "
            + json.dumps(input_schema, separators=(",", ":"), sort_keys=True)
            if isinstance(input_schema, dict)
            else ""
        )

        def request(
            arguments: dict[str, Any],
            *,
            _tool=tool_name,
            _action=action,
            _version=version,
        ) -> str:
            return ToolRequest(
                tool=_tool,
                action=_action,
                version=_version,
                arguments=arguments,
            ).model_dump_json()

        tools.append(
            StructuredTool.from_function(
                func=request,
                name=f"registered_{re.sub(r'[^A-Za-z0-9_-]', '_', name)[:40]}_{index}",
                description=f"Request registered tool {name}@{version}. {description}",
                args_schema=_RegisteredToolInput,
            )
        )
    return tuple(tools)


SERVER_AGENT_PROMPT = """You are the server-side DevOps Agent.

Use the registered tools provided to you to perform actions on the user's
configured systems. When a listed tool can fulfill the request, call it; do not
claim that you cannot access or execute on the user's system. These tools are
the only execution path: never run commands, access files, or invent tools
yourself. If no listed tool supports the request, say that the required
registered capability is unavailable in this deployment. Do not put secrets in
tool arguments. Use tool results and conversation context as the source of truth.
"""


def _default_model() -> Any:
    """Load the configured model lazily so importing this module is testable."""

    from agent_server.llms import DEFAULT_MODEL
    return DEFAULT_MODEL


@dataclass
class ServerAgent:
    """Asynchronous request-producing agent with an injectable model."""

    model: Any | None = None
    checkpointer: Any | None = None

    def __post_init__(self) -> None:
        self._graph = None

    def _get_graph(self, available_tools: Sequence[Mapping[str, Any]]) -> Any:
        # Tool catalogs are user-scope-filtered, so never reuse a graph with a
        # different user's tool set.
        return create_agent(
            model=self.model or _default_model(),
            tools=list(registered_request_tools(available_tools)),
            system_prompt=SERVER_AGENT_PROMPT,
            context_schema=SessionContext,
            name="server_devops_agent",
            checkpointer=self.checkpointer,
        )

    async def arun(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        history: Sequence[BaseMessage] | None = None,
        tool_results: Sequence[Mapping[str, Any]] = (),
        run_id: str | None = None,
        correlation_id: str = "",
        traceparent: str | None = None,
        available_tools: Sequence[Mapping[str, Any]] = (),
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> "AgentResponse":
        """Process one message without executing any requested operation."""

        context = SessionContext(user_id=user_id, session_id=session_id)
        if not message.strip():
            raise ValueError("message must not be empty")
        messages = list(history or ())
        messages.append(HumanMessage(content=message))
        for result in tool_results:
            call_id = result.get("call_id")
            if not isinstance(call_id, str) or not call_id:
                raise ValueError("Tool results require a call_id")
            messages.append(
                ToolMessage(content=json.dumps(dict(result), separators=(",", ":")), tool_call_id=call_id)
            )
        graph = self._get_graph(available_tools)
        input_state = {"messages": messages}
        config = {
            "configurable": {"thread_id": session_id},
            "metadata": {
                key: value
                for key, value in {
                    "run_id": run_id,
                    "correlation_id": correlation_id,
                    "traceparent": traceparent,
                }.items()
                if value
            },
            "run_name": "devops_agent_turn",
        }
        if on_event is None:
            result = await graph.ainvoke(input_state, context=context.model_dump(), config=config)
        else:
            result = None
            async for mode, chunk in graph.astream(
                input_state,
                context=context.model_dump(),
                config=config,
                stream_mode=["messages", "values"],
            ):
                if mode == "messages":
                    message, _metadata = chunk
                    if isinstance(message, AIMessageChunk):
                        text = _message_text(message.content)
                        if text:
                            await on_event({"type": "agent_delta", "text": text})
                elif mode == "values":
                    result = chunk
            if result is None:
                raise RuntimeError("Agent stream finished without a final state")
        return AgentResponse.from_result(result, context=context)


@dataclass(frozen=True)
class AgentResponse:
    """Stable server response containing validated requests and final text."""

    context: SessionContext
    message: str
    requests: tuple[ToolRequest, ...]

    @classmethod
    def from_result(cls, result: Mapping[str, Any], *, context: SessionContext) -> "AgentResponse":
        messages = result.get("messages", ())
        requests: list[ToolRequest] = []
        for item in messages:
            if not isinstance(item, ToolMessage):
                continue
            try:
                payload = json.loads(item.content) if isinstance(item.content, str) else item.content
                request = ToolRequest.model_validate(payload)
                requests.append(request.model_copy(update={"call_id": item.tool_call_id}))
            except (TypeError, ValueError, ValidationError):
                continue

        final_message = ""
        for item in reversed(messages):
            content = getattr(item, "content", None)
            if content and not isinstance(item, ToolMessage):
                final_message = content if isinstance(content, str) else json.dumps(content)
                break
        return cls(context=context, message=final_message, requests=tuple(requests))


async def run_agent(
    user_id: str,
    session_id: str,
    message: str,
    *,
    model: Any | None = None,
    history: Sequence[BaseMessage] | None = None,
) -> AgentResponse:
    """Convenience asynchronous entry point for HTTP/websocket handlers."""

    return await ServerAgent(model=model).arun(
        user_id=user_id,
        session_id=session_id,
        message=message,
        history=history,
    )


__all__ = ["AgentResponse", "SERVER_AGENT_PROMPT", "ServerAgent", "SessionContext", "ToolRequest", "registered_request_tools", "run_agent"]


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
        )
    return ""
