"""Persist ordered conversation timelines across runs."""

from alembic import op
import sqlalchemy as sa

revision = "0008_conversation_events"
down_revision = "0007_durable_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_events",
        sa.Column("sequence", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_conversation_events_conversation_sequence",
        "conversation_events",
        ["conversation_id", "sequence"],
    )
    op.create_index("ix_conversation_events_run_id", "conversation_events", ["run_id"])
    op.execute(
        """
        WITH history AS (
            SELECT
                md5('message:' || m.id) AS id,
                m.conversation_id,
                linked_run.id AS run_id,
                m.role || '_message' AS event_type,
                json_build_object(
                    'message_id', m.id, 'role', m.role, 'content', m.content
                ) AS data,
                m.created_at,
                0 AS event_order,
                m.sequence AS source_order
            FROM conversation_messages AS m
            LEFT JOIN agent_runs AS linked_run ON linked_run.message_id = m.id
            WHERE NOT (
                m.role = 'assistant' AND EXISTS (
                    SELECT 1 FROM agent_runs AS completed_run
                    WHERE completed_run.conversation_id = m.conversation_id
                      AND completed_run.message = m.content
                      AND completed_run.message <> ''
                )
            )
            UNION ALL
            SELECT
                md5('run-event:' || re.sequence::text),
                r.conversation_id,
                r.id,
                CASE re.event_type
                    WHEN 'created' THEN 'run_created'
                    WHEN 'running' THEN 'run_started'
                    WHEN 'resumed' THEN 'run_resumed'
                    WHEN 'completed' THEN 'run_completed'
                    WHEN 'failed' THEN 'run_failed'
                    WHEN 'cancelled' THEN 'run_cancelled'
                    ELSE re.event_type
                END,
                CASE
                    WHEN re.event_type = 'completed' THEN
                        json_build_object('state', re.data ->> 'state')
                    WHEN re.event_type = 'tool_call_completed' THEN
                        jsonb_set(
                            jsonb_set(
                                re.data::jsonb,
                                '{result,output}',
                                CASE
                                    WHEN length((re.data::jsonb #> '{result,output}')::text) > 16000
                                    THEN jsonb_build_object(
                                        'preview', left((re.data::jsonb #> '{result,output}')::text, 16000),
                                        'truncated', true,
                                        'original_chars', length((re.data::jsonb #> '{result,output}')::text)
                                    )
                                    ELSE coalesce(re.data::jsonb #> '{result,output}', 'null'::jsonb)
                                END
                            ),
                            '{result,error}',
                            CASE
                                WHEN length(re.data::jsonb #>> '{result,error}') > 16000
                                THEN to_jsonb(left(re.data::jsonb #>> '{result,error}', 16000) || ' … [truncated]')
                                ELSE coalesce(re.data::jsonb #> '{result,error}', 'null'::jsonb)
                            END
                        )::json
                    ELSE re.data
                END,
                re.created_at,
                2,
                re.sequence
            FROM run_events AS re
            JOIN agent_runs AS r ON r.id = re.run_id
            UNION ALL
            SELECT
                md5('assistant:' || r.id),
                r.conversation_id,
                r.id,
                'assistant_message',
                json_build_object(
                    'message_id', message_row.id,
                    'role', 'assistant',
                    'content', r.message
                ),
                r.updated_at,
                1,
                0::bigint
            FROM agent_runs AS r
            JOIN conversation_messages AS message_row
              ON message_row.conversation_id = r.conversation_id
             AND message_row.role = 'assistant'
             AND message_row.content = r.message
             AND message_row.created_at = r.updated_at
            WHERE r.message <> '' AND r.state = 'completed'
        )
        INSERT INTO conversation_events
            (id, conversation_id, run_id, event_type, data, created_at)
        SELECT id, conversation_id, run_id, event_type, data, created_at
        FROM history
        ORDER BY created_at, event_order, source_order
        """
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_events_run_id", table_name="conversation_events")
    op.drop_index(
        "ix_conversation_events_conversation_sequence", table_name="conversation_events"
    )
    op.drop_table("conversation_events")
