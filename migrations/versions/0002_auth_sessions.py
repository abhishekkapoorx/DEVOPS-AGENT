"""Persist browser device grants and rotating refresh sessions."""

from alembic import op
import sqlalchemy as sa


revision = "0002_auth_sessions"
down_revision = "0001_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_device_authorizations",
        sa.Column("device_code_hash", sa.String(64), primary_key=True),
        sa.Column("user_code", sa.String(16), nullable=False, unique=True),
        sa.Column("approval_id", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_auth_device_authorizations_user_code", "auth_device_authorizations", ["user_code"])
    op.create_index("ix_auth_device_authorizations_approval_id", "auth_device_authorizations", ["approval_id"])
    op.create_index("ix_auth_device_authorizations_status", "auth_device_authorizations", ["status"])
    op.create_index("ix_auth_device_authorizations_expires_at", "auth_device_authorizations", ["expires_at"])
    op.create_table(
        "auth_sessions",
        sa.Column("session_id", sa.String(32), primary_key=True),
        sa.Column("family_id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by", sa.String(32)),
    )
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_family_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_auth_device_authorizations_expires_at", table_name="auth_device_authorizations")
    op.drop_index("ix_auth_device_authorizations_status", table_name="auth_device_authorizations")
    op.drop_index("ix_auth_device_authorizations_approval_id", table_name="auth_device_authorizations")
    op.drop_index("ix_auth_device_authorizations_user_code", table_name="auth_device_authorizations")
    op.drop_table("auth_device_authorizations")
