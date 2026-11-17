"""Add durable alert, investigation, evidence, and audit records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_investigations"
down_revision = "0009_raw_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("alertname", sa.String(255), nullable=False),
        sa.Column("namespace", sa.String(255)),
        sa.Column("workload", sa.String(255)),
        sa.Column("severity", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("occurrence_count", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("attempt_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.BigInteger(), nullable=False, server_default="3"),
        sa.Column("locked_by", sa.String(128)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("slack_posted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'completed_degraded', 'failed', 'closed')",
            name="ck_investigations_status",
        ),
    )
    op.create_index("ix_investigations_fingerprint", "investigations", ["fingerprint"])
    op.create_index("ix_investigations_status", "investigations", ["status"])
    op.create_index("ix_investigations_run_after", "investigations", ["run_after"])
    op.create_index(
        "uq_investigations_open_fingerprint",
        "investigations",
        ["fingerprint"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'running', 'completed', 'completed_degraded')"
        ),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("delivery_key", sa.String(64), nullable=False, unique=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.String(255)),
        sa.Column("alertname", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("namespace", sa.String(255)),
        sa.Column("workload", sa.String(255)),
        sa.Column("pod", sa.String(255)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("labels", postgresql.JSONB(), nullable=False),
        sa.Column("annotations", postgresql.JSONB(), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "investigation_id",
            sa.String(32),
            sa.ForeignKey("investigations.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_alerts_fingerprint", "alerts", ["fingerprint"])
    op.create_index("ix_alerts_source", "alerts", ["source"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_received_at", "alerts", ["received_at"])
    op.create_index("ix_alerts_investigation_id", "alerts", ["investigation_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(128), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_object_id", "audit_log", ["object_id"])

    op.create_table(
        "investigation_evidence",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "investigation_id",
            sa.String(32),
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_ref", sa.String(255), nullable=False),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "investigation_id", "source", "query_hash", name="uq_investigation_evidence_query"
        ),
    )
    op.create_index("ix_investigation_evidence_investigation_id", "investigation_evidence", ["investigation_id"])
    op.create_index("ix_investigation_evidence_source", "investigation_evidence", ["source"])


def downgrade() -> None:
    op.drop_index("ix_investigation_evidence_source", table_name="investigation_evidence")
    op.drop_index("ix_investigation_evidence_investigation_id", table_name="investigation_evidence")
    op.drop_table("investigation_evidence")
    op.drop_index("ix_audit_log_object_id", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_ts", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_alerts_investigation_id", table_name="alerts")
    op.drop_index("ix_alerts_received_at", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_source", table_name="alerts")
    op.drop_index("ix_alerts_fingerprint", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("uq_investigations_open_fingerprint", table_name="investigations")
    op.drop_index("ix_investigations_run_after", table_name="investigations")
    op.drop_index("ix_investigations_status", table_name="investigations")
    op.drop_index("ix_investigations_fingerprint", table_name="investigations")
    op.drop_table("investigations")
