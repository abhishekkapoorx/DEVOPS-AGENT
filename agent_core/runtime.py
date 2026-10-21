"""Stable application-facing interface for pluggable agent implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class AgentToolCall:
    """A typed request for a registered capability produced by an agent."""

    call_id: str
    name: str
    version: str = "1.0.0"
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRequest:
    """One agent turn, with identities supplied by the authenticated backend."""

    user_id: str
    conversation_id: str
    run_id: str
    message: str
    history: Sequence[Mapping[str, Any]] = ()
    tool_results: Sequence[Mapping[str, Any]] = ()
    available_tools: Sequence[Mapping[str, Any]] = ()
    correlation_id: str = ""
    traceparent: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id or not self.conversation_id or not self.run_id:
            raise ValueError("user_id, conversation_id, and run_id are required")
        if not self.message.strip():
            raise ValueError("message must not be empty")


@dataclass(frozen=True)
class AgentResponse:
    """Framework-neutral result from one agent turn."""

    message: str
    tool_calls: tuple[AgentToolCall, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class AgentRuntime(Protocol):
    """An implementation capable of running an agent turn."""

    async def run(self, request: AgentRequest) -> AgentResponse:
        """Run one turn and return its message and requested capabilities."""
        ...
