"""Persist browser device-approval decisions across API restarts."""

from alembic import op
import sqlalchemy as sa


revision = "0007_durable_approvals"
down_revision = "0006_local_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_device_authorizations", sa.Column("approval_status", sa.String(length=16), nullable=True))
    op.add_column("auth_device_authorizations", sa.Column("approved_user_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_device_authorizations", "approved_user_id")
    op.drop_column("auth_device_authorizations", "approval_status")
