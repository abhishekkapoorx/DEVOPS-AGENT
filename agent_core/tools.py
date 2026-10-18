"""Project-owned contracts for registered tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    required_scopes: frozenset[str] = frozenset()
    timeout_seconds: float = 30.0
    requires_approval: bool = False


@dataclass(frozen=True)
class ToolExecutionContext:
    user_id: str
    run_id: str
    call_id: str
    scopes: frozenset[str]
    approved: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    status: Literal["succeeded", "failed", "rejected", "approval_required", "running"]
    output: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


class RegisteredTool(Protocol):
    async def execute(
        self, arguments: BaseModel, context: ToolExecutionContext
    ) -> BaseModel: ...


ToolFactory = Callable[[ToolExecutionContext], RegisteredTool]


__all__ = [
    "RegisteredTool",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolFactory",
    "ToolResult",
]
