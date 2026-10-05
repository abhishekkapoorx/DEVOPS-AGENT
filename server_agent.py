"""Server-side DevOps agent.

This module contains the cloud-facing boundary for the project. It may decide
that an operation is needed, but it never performs that operation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError


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
    arguments: dict[str, Any] = Field(default_factory=dict)


class _ToolRequestInput(BaseModel):
    action: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    arguments: dict[str, Any] = Field(default_factory=dict)


def _request_tool(tool_name: str, description: str) -> StructuredTool:
    """Build a tool that records intent instead of executing an operation."""

    def request(action: str, arguments: dict[str, Any] | None = None) -> str:
        return ToolRequest(
            tool=tool_name,
            action=action,
            arguments=arguments or {},
        ).model_dump_json()

    return StructuredTool.from_function(
        func=request,
        name=tool_name,
        description=description,
        args_schema=_ToolRequestInput,
    )


REQUEST_TOOLS = (
    _request_tool("cloud", "Request an AWS, Azure, or GCP operation. Never execute it."),
    _request_tool("docker", "Request a Docker or container operation. Never invoke Docker."),
    _request_tool("kubernetes", "Request a Kubernetes or Helm operation. Never invoke kubectl or Helm."),
    _request_tool("files", "Request a file or code operation. Never access the local filesystem."),
)


SERVER_AGENT_PROMPT = """You are the server-side DevOps Agent.

Understand the user's request and provide an answer or create structured tool
requests. You are a planner and request producer, not an executor. You must
never run shell commands, cloud CLIs, Docker, kubectl, Helm, or access files.
For operations, call the matching request tool with a concise action and
JSON-compatible arguments. Do not put secrets in arguments. Use the user's
request and session context as the source of truth.
"""


def _default_model() -> Any:
    """Load the configured model lazily so importing this module is testable."""

    from llms import DEFAULT_MODEL
    return DEFAULT_MODEL


@dataclass
class ServerAgent:
    """Asynchronous request-producing agent with an injectable model."""

    model: Any | None = None

    def __post_init__(self) -> None:
        self._graph = None

    def _get_graph(self) -> Any:
        if self._graph is None:
            self._graph = create_agent(
                model=self.model or _default_model(),
                tools=list(REQUEST_TOOLS),
                system_prompt=SERVER_AGENT_PROMPT,
                context_schema=SessionContext,
                name="server_devops_agent",
            )
        return self._graph

    async def arun(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        history: Sequence[BaseMessage] | None = None,
    ) -> "AgentResponse":
        """Process one message without executing any requested operation."""

        context = SessionContext(user_id=user_id, session_id=session_id)
        if not message.strip():
            raise ValueError("message must not be empty")
        messages = list(history or ())
        messages.append(HumanMessage(content=message))
        result = await self._get_graph().ainvoke(
            {"messages": messages},
            context=context.model_dump(),
        )
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
                requests.append(ToolRequest.model_validate(payload))
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


__all__ = ["AgentResponse", "REQUEST_TOOLS", "SERVER_AGENT_PROMPT", "ServerAgent", "SessionContext", "ToolRequest", "run_agent"]
