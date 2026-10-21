"""Persist local email/password accounts."""

from alembic import op
import sqlalchemy as sa


revision = "0006_local_accounts"
down_revision = "0005_trace_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_accounts",
        sa.Column("email", sa.String(length=320), primary_key=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_accounts")
