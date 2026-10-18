import ast
from pathlib import Path

from agent_server.persistence.postgres import AgentRunRow, Base, RunEventRow


def test_postgres_metadata_contains_idempotency_and_restart_lease_fields():
    run_table = Base.metadata.tables["agent_runs"]
    columns = set(run_table.columns.keys())

    assert {"idempotency_key", "request_hash", "input_message", "attempt", "lease_owner", "lease_expires_at"} <= columns
    assert any(
        constraint.name == "uq_agent_run_idempotency"
        for constraint in run_table.constraints
    )
    assert RunEventRow.__tablename__ == "run_events"
    assert AgentRunRow.__tablename__ == "agent_runs"


def test_run_migration_follows_auth_and_creates_leased_run_tables():
    migration_path = Path("migrations/versions/0003_agent_runs.py")
    module = ast.parse(migration_path.read_text(encoding="utf-8"))
    assignments = {
        item.targets[0].id: ast.literal_eval(item.value)
        for item in module.body
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
        and item.targets[0].id in {"revision", "down_revision"}
    }

    assert assignments == {"revision": "0003_agent_runs", "down_revision": "0002_auth_sessions"}
    assert "lease_expires_at" in migration_path.read_text(encoding="utf-8")
    assert {"correlation_id", "traceparent"} <= set(AgentRunRow.__table__.columns.keys())
