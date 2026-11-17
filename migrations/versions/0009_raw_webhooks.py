"""Persist raw Alertmanager webhook payloads for audit and replay."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_raw_webhooks"
down_revision = "0008_conversation_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_webhooks",
        sa.Column("id", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headers", postgresql.JSONB(), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_raw_webhooks_received_at", "raw_webhooks", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_raw_webhooks_received_at", table_name="raw_webhooks")
    op.drop_table("raw_webhooks")
