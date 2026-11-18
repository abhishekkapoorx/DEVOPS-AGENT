import ast
import asyncio
from pathlib import Path

from agent_server.persistence.postgres import (
    AgentRunRow,
    Base,
    ConversationEventRow,
    ConversationRow,
    MessageRow,
    PostgresConversationRepository,
    RawWebhookRow,
    RunEventRow,
)


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
    assert "conversation_events" in Base.metadata.tables
    assert ConversationEventRow.__tablename__ == "conversation_events"
    assert RawWebhookRow.__tablename__ == "raw_webhooks"
    assert {"id", "received_at", "headers", "body"} <= set(
        RawWebhookRow.__table__.columns.keys()
    )


def test_conversation_event_migration_backfills_existing_messages_and_run_events():
    migration_path = Path("migrations/versions/0008_conversation_events.py")
    source = migration_path.read_text(encoding="utf-8")
    module = ast.parse(source)
    assignments = {
        item.targets[0].id: ast.literal_eval(item.value)
        for item in module.body
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
        and item.targets[0].id in {"revision", "down_revision"}
    }

    assert assignments == {
        "revision": "0008_conversation_events",
        "down_revision": "0007_durable_approvals",
    }
    assert "FROM conversation_messages" in source
    assert "FROM run_events" in source
    assert "ORDER BY created_at" in source
    assert "'{result,output}'" in source
    assert "16000" in source


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


def test_run_persistence_flushes_user_message_before_dependent_run():
    class Session:
        def __init__(self):
            self.query_count = 0
            self.pending = []
            self.flushes = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def scalar(self, _query):
            self.query_count += 1
            if self.query_count == 1:
                return ConversationRow(
                    id="conversation", user_id="user", title="test",
                    created_at=None, updated_at=None,
                )
            return None

        def add(self, row):
            self.pending.append(row)

        async def flush(self):
            self.flushes.append(tuple(type(row) for row in self.pending))
            self.pending.clear()

        async def commit(self):
            pass

    session = Session()
    repository = PostgresConversationRepository(lambda: session)
    run, created = asyncio.run(
        repository.create_or_get_run("user", "conversation", "key", "hash", "hi")
    )

    assert created is True
    assert run.input_message == "hi"
    assert session.flushes[:2] == [(MessageRow,), (AgentRunRow,)]
    timeline = [row for row in session.pending if isinstance(row, ConversationEventRow)]
    assert [row.event_type for row in timeline] == ["user_message", "run_created"]
    assert timeline[0].data["message_id"] == run.message_id
