import ast
from pathlib import Path

from agent_server.persistence.postgres import Base
from agent_server.persistence.tool_audit import ToolExecutionRow


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
