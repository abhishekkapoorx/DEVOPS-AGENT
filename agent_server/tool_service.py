"""Factory-backed tool registry and policy-enforcing execution service."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from pydantic import ValidationError

from agent_core.tools import (
    RegisteredTool,
    ToolDefinition,
    ToolExecutionContext,
    ToolFactory,
    ToolResult,
)


@dataclass(frozen=True)
class _Registration:
    definition: ToolDefinition
    factory: ToolFactory


class ToolRegistry:
    """Resolves a stable name/version to a definition and adapter factory."""

    def __init__(self) -> None:
        self._registrations: dict[tuple[str, str], _Registration] = {}

    def register(self, definition: ToolDefinition, factory: ToolFactory) -> None:
        if not definition.name or not definition.version:
            raise ValueError("tool name and version are required")
        if definition.timeout_seconds <= 0:
            raise ValueError("tool timeout must be positive")
        key = (definition.name, definition.version)
        if key in self._registrations:
            raise ValueError(f"tool already registered: {definition.name}@{definition.version}")
        self._registrations[key] = _Registration(definition, factory)

    def resolve(self, name: str, version: str) -> _Registration | None:
        return self._registrations.get((name, version))

    def list_tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            registration.definition
            for _, registration in sorted(self._registrations.items())
        )


class ToolService:
    """Validate, authorize, instantiate, and execute registered tools."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def list_tools(self, scopes: frozenset[str]) -> tuple[ToolDefinition, ...]:
        return tuple(
            definition
            for definition in self._registry.list_tools()
            if definition.required_scopes <= scopes
        )

    async def execute(
        self,
        *,
        name: str,
        version: str,
        arguments: dict,
        context: ToolExecutionContext,
    ) -> ToolResult:
        registration = self._registry.resolve(name, version)
        if registration is None:
            return ToolResult(context.call_id, name, "rejected", error="Unknown tool")
        definition = registration.definition
        if not definition.required_scopes <= context.scopes:
            return ToolResult(context.call_id, name, "rejected", error="Tool is not authorized")
        if definition.requires_approval and not context.approved:
            return ToolResult(context.call_id, name, "approval_required")
        try:
            validated = definition.input_model.model_validate(arguments)
        except ValidationError:
            return ToolResult(context.call_id, name, "rejected", error="Invalid tool arguments")

        started = time.perf_counter()
        try:
            tool: RegisteredTool = registration.factory(context)
            output = await asyncio.wait_for(
                tool.execute(validated, context), timeout=definition.timeout_seconds
            )
            validated_output = definition.output_model.model_validate(output)
        except TimeoutError:
            return ToolResult(
                context.call_id,
                name,
                "failed",
                error="Tool execution timed out",
                duration_ms=_duration(started),
            )
        except ValidationError:
            return ToolResult(
                context.call_id,
                name,
                "failed",
                error="Tool returned an invalid result",
                duration_ms=_duration(started),
            )
        except Exception:
            return ToolResult(
                context.call_id,
                name,
                "failed",
                error="Tool execution failed",
                duration_ms=_duration(started),
            )
        return ToolResult(
            context.call_id,
            name,
            "succeeded",
            output=validated_output.model_dump(mode="json"),
            duration_ms=_duration(started),
        )


def _duration(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


__all__ = ["ToolRegistry", "ToolService"]
