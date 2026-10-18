import pytest
from pathlib import Path
from pydantic import BaseModel

from agent_core.tools import ToolDefinition, ToolExecutionContext
from agent_server.tool_service import ToolRegistry, ToolService
from agent_server.registered_tools import build_default_registry


class Input(BaseModel):
    value: str


class Output(BaseModel):
    value: str


class EchoTool:
    async def execute(self, arguments, context):
        return Output(value=arguments.value)


def definition(**changes):
    values = dict(
        name="echo",
        version="1.0.0",
        description="Return the input",
        input_model=Input,
        output_model=Output,
    )
    values.update(changes)
    return ToolDefinition(**values)


@pytest.mark.asyncio
async def test_tool_service_validates_and_executes_a_registered_factory():
    registry = ToolRegistry()
    registry.register(definition(required_scopes=frozenset({"tools:echo"})), lambda _: EchoTool())
    service = ToolService(registry)

    result = await service.execute(
        name="echo",
        version="1.0.0",
        arguments={"value": "hello"},
        context=ToolExecutionContext(
            user_id="user-1", run_id="run-1", call_id="call-1", scopes=frozenset({"tools:echo"}),
            correlation_id="corr-1", idempotency_key="idem-1", traceparent="00-abc-def-01",
        ),
    )

    assert result.status == "succeeded"
    assert result.output == {"value": "hello"}


@pytest.mark.asyncio
async def test_tool_service_rejects_missing_scope_and_destructive_unapproved_call():
    registry = ToolRegistry()
    registry.register(
        definition(risk_class="destructive", required_scopes=frozenset({"tools:echo"})),
        lambda _: EchoTool(),
    )
    service = ToolService(registry)
    context = ToolExecutionContext(
        user_id="user-1", run_id="run-1", call_id="call-1", scopes=frozenset()
    )

    denied = await service.execute(name="echo", version="1.0.0", arguments={"value": "x"}, context=context)
    assert denied.status == "rejected"

    authorized = context.__class__(
        user_id="user-1", run_id="run-1", call_id="call-2", scopes=frozenset({"tools:echo"})
    )
    approval = await service.execute(
        name="echo", version="1.0.0", arguments={"value": "x"}, context=authorized
    )
    assert approval.status == "approval_required"


@pytest.mark.asyncio
async def test_tool_service_rejects_outputs_over_definition_limit():
    registry = ToolRegistry()
    registry.register(definition(max_result_bytes=8), lambda _: EchoTool())
    result = await ToolService(registry).execute(
        name="echo",
        version="1.0.0",
        arguments={"value": "too long"},
        context=ToolExecutionContext(user_id="u", run_id="r", call_id="c", scopes=frozenset()),
    )
    assert result.status == "failed"
    assert result.error == "Tool result exceeded the configured size limit"


def test_registry_rejects_invalid_execution_limits_and_duplicate_versions():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="execution limits"):
        registry.register(definition(max_retries=-1), lambda _: EchoTool())
    registry.register(definition(), lambda _: EchoTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition(), lambda _: EchoTool())


@pytest.mark.asyncio
async def test_retryable_tool_requires_idempotency_and_reuses_factory_per_attempt():
    class Flaky:
        def __init__(self):
            self.attempts = 0

        async def execute(self, arguments, context):
            self.attempts += 1
            if self.attempts == 1:
                raise TimeoutError
            return Output(value=arguments.value)

    adapters = []

    def factory(_):
        adapter = Flaky()
        adapters.append(adapter)
        return adapter

    registry = ToolRegistry()
    registry.register(definition(max_retries=1), factory)
    service = ToolService(registry)
    rejected = await service.execute(
        name="echo",
        version="1.0.0",
        arguments={"value": "safe"},
        context=ToolExecutionContext(user_id="u", run_id="r", call_id="c0", scopes=frozenset()),
    )
    result = await service.execute(
        name="echo",
        version="1.0.0",
        arguments={"value": "safe"},
        context=ToolExecutionContext(
            user_id="u", run_id="r", call_id="c1", scopes=frozenset(), idempotency_key="idem"
        ),
    )

    assert rejected.status == "rejected"
    assert result.status == "succeeded"
    assert len(adapters) == 1


def test_default_registry_exposes_only_read_only_git_status_by_factory():
    registry = build_default_registry({"repo-1": Path("/workspace/repo")})
    tools = registry.list_tools()
    assert [(tool.name, tool.version, tool.risk_class) for tool in tools] == [
        ("git.status", "1.0.0", "read_only")
    ]
