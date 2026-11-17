"""Persist investigation results and LLM run telemetry."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_llm_runs_and_reports"
down_revision = "0010_investigations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investigations", sa.Column("result", postgresql.JSONB()))
    op.add_column("investigations", sa.Column("verifier_report", postgresql.JSONB()))
    op.create_table(
        "investigation_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "investigation_id",
            sa.String(32),
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("tokens_in", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_investigation_runs_investigation_id", "investigation_runs", ["investigation_id"])


def downgrade() -> None:
    op.drop_index("ix_investigation_runs_investigation_id", table_name="investigation_runs")
    op.drop_table("investigation_runs")
    op.drop_column("investigations", "verifier_report")
    op.drop_column("investigations", "result")
