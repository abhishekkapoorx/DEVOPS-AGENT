"""Persist correlation and W3C trace context with Agent Runs."""

from alembic import op
import sqlalchemy as sa

revision = "0005_trace_context"
down_revision = "0004_tool_execution_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("correlation_id", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("agent_runs", sa.Column("traceparent", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "traceparent")
    op.drop_column("agent_runs", "correlation_id")
