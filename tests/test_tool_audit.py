import ast
from pathlib import Path

import pytest

from agent_core.tools import ToolDefinition, ToolExecutionContext
from agent_server.persistence.postgres import Base
from agent_server.persistence.tool_audit import ToolExecutionRow
from agent_server.tool_service import ToolRegistry, ToolService


class Arguments:
    def __init__(self, value):
        self.value = value


class Output:
    def __init__(self, value):
        self.value = value

    def model_dump(self, mode="python"):
        return {"value": self.value}


class InputModel:
    @classmethod
    def model_validate(cls, value):
        return Arguments(value["value"])


class OutputModel:
    @classmethod
    def model_validate(cls, value):
        return value if isinstance(value, Output) else Output(value["value"])


class Echo:
    def __init__(self):
        self.calls = 0

    async def execute(self, args, context):
        self.calls += 1
        return Output(args.value)


class Audit:
    def __init__(self):
        self.saved = {}
        self.started = 0
        self.finished = 0

    async def begin_tool_call(self, context, name, version, arguments):
        self.started += 1
        return self.saved.get(context.idempotency_key)

    async def finish_tool_call(self, context, result):
        self.finished += 1
        self.saved[context.idempotency_key] = result


@pytest.mark.asyncio
async def test_tool_service_wraps_execution_in_idempotent_audit_lifecycle():
    audit = Audit()
    registry = ToolRegistry()
    adapters = []

    def factory(_):
        adapter = Echo()
        adapters.append(adapter)
        return adapter

    registry.register(
        ToolDefinition(
            name="echo",
            version="1",
            description="echo",
            input_model=InputModel,
            output_model=OutputModel,
        ),
        factory,
    )
    service = ToolService(registry, audit_repository=audit)
    context = ToolExecutionContext(
        user_id="u", run_id="r", call_id="c", scopes=frozenset(), idempotency_key="idem"
    )

    first = await service.execute(name="echo", version="1", arguments={"value": "x"}, context=context)
    duplicate = await service.execute(name="echo", version="1", arguments={"value": "x"}, context=context)

    assert first.status == duplicate.status == "succeeded"
    assert sum(adapter.calls for adapter in adapters) == 1
    assert audit.started == 2
    assert audit.finished == 1


def test_postgres_metadata_and_migration_include_durable_tool_audit():
    table = Base.metadata.tables["tool_executions"]
    assert {"idempotency_key", "request_hash", "arguments", "result", "status"} <= set(table.columns.keys())
    assert ToolExecutionRow.__tablename__ == "tool_executions"
    path = Path("migrations/versions/0004_tool_execution_audit.py")
    module = ast.parse(path.read_text(encoding="utf-8"))
    assignments = {
        item.targets[0].id: ast.literal_eval(item.value)
        for item in module.body
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
        and item.targets[0].id in {"revision", "down_revision"}
    }
    assert assignments == {
        "revision": "0004_tool_execution_audit",
        "down_revision": "0003_agent_runs",
    }
