"""Factory-backed tool registry and policy-enforcing execution service."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from agent_core.tools import (
    RegisteredTool,
    ToolDefinition,
    ToolExecutionContext,
    ToolFactory,
    ToolResult,
)


class ToolExecutionRepository(Protocol):
    async def begin_tool_call(
        self, context: ToolExecutionContext, name: str, version: str, arguments: dict
    ) -> ToolResult | None: ...

    async def finish_tool_call(
        self, context: ToolExecutionContext, result: ToolResult
    ) -> None: ...


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
        if (
            definition.timeout_seconds <= 0
            or definition.max_retries < 0
            or definition.max_result_bytes <= 0
            or definition.max_concurrency < 1
        ):
            raise ValueError("tool execution limits must be positive and retries non-negative")
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

    def __init__(
        self, registry: ToolRegistry, *, audit_repository: ToolExecutionRepository | None = None
    ) -> None:
        self._registry = registry
        self._audit_repository = audit_repository
        self._semaphores: dict[tuple[str, str], asyncio.Semaphore] = {}

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
        if self._audit_repository is not None:
            if not context.idempotency_key:
                raise ValueError("audited Tool Calls require an idempotency key")
            existing = await self._audit_repository.begin_tool_call(
                context, name, version, arguments
            )
            if existing is not None:
                return existing
        try:
            result = await self._execute(
                name=name, version=version, arguments=arguments, context=context
            )
        except asyncio.CancelledError:
            if self._audit_repository is not None:
                await asyncio.shield(
                    self._audit_repository.finish_tool_call(
                        context,
                        ToolResult(
                            context.call_id,
                            name,
                            "cancelled",
                            error="Tool execution was cancelled",
                        ),
                    )
                )
            raise
        if self._audit_repository is not None:
            await self._audit_repository.finish_tool_call(context, result)
        return result

    async def _execute(
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
        if (definition.requires_approval or definition.risk_class == "destructive") and not context.approved:
            return ToolResult(context.call_id, name, "approval_required")
        if definition.max_retries and not context.idempotency_key:
            return ToolResult(context.call_id, name, "rejected", error="Idempotency key required for retries")
        try:
            validated = definition.input_model.model_validate(arguments)
        except ValidationError:
            return ToolResult(context.call_id, name, "rejected", error="Invalid tool arguments")

        started = time.perf_counter()
        key = (name, version)
        semaphore = self._semaphores.setdefault(
            key, asyncio.Semaphore(definition.max_concurrency)
        )
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=definition.timeout_seconds)
        except TimeoutError:
            return ToolResult(
                context.call_id,
                name,
                "failed",
                error="Tool concurrency limit wait timed out",
                duration_ms=_duration(started),
            )
        try:
            try:
                output = None
                tool: RegisteredTool = registration.factory(context)
                for attempt in range(definition.max_retries + 1):
                    try:
                        output = await asyncio.wait_for(
                            tool.execute(validated, context), timeout=definition.timeout_seconds
                        )
                        break
                    except TimeoutError:
                        if attempt == definition.max_retries:
                            raise
                validated_output = definition.output_model.model_validate(output)
                serialized_output = json.dumps(
                    validated_output.model_dump(mode="json"), separators=(",", ":")
                ).encode("utf-8")
                if len(serialized_output) > definition.max_result_bytes:
                    return ToolResult(
                        context.call_id,
                        name,
                        "failed",
                        error="Tool result exceeded the configured size limit",
                        duration_ms=_duration(started),
                    )
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
        finally:
            semaphore.release()
        return ToolResult(
            context.call_id,
            name,
            "succeeded",
            output=validated_output.model_dump(mode="json"),
            duration_ms=_duration(started),
        )


def _duration(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


__all__ = ["ToolExecutionRepository", "ToolRegistry", "ToolService"]
