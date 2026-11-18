"""Add tenant ownership and encrypted user secret records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_user_secrets_and_ownership"
down_revision = "0011_llm_runs_and_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("raw_webhooks", "alerts", "investigations"):
        op.add_column(
            table,
            sa.Column("owner_user_id", sa.String(255), nullable=False, server_default="system"),
        )
        op.create_index(f"ix_{table}_owner_user_id", table, ["owner_user_id"])

    op.drop_index("uq_investigations_open_fingerprint", table_name="investigations")
    op.create_index(
        "uq_investigations_open_owner_fingerprint",
        "investigations",
        ["owner_user_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'running', 'completed', 'completed_degraded')"
        ),
    )

    op.create_table(
        "webhook_secrets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "name", name="uq_webhook_secrets_user_name"),
    )
    op.create_index("ix_webhook_secrets_user_id", "webhook_secrets", ["user_id"])

    op.create_table(
        "user_secrets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "provider", "name", name="uq_user_secrets_user_provider_name"
        ),
    )
    op.create_index("ix_user_secrets_user_id", "user_secrets", ["user_id"])
    op.create_index("ix_user_secrets_updated_at", "user_secrets", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_user_secrets_updated_at", table_name="user_secrets")
    op.drop_index("ix_user_secrets_user_id", table_name="user_secrets")
    op.drop_table("user_secrets")
    op.drop_index("ix_webhook_secrets_user_id", table_name="webhook_secrets")
    op.drop_table("webhook_secrets")
    op.drop_index("uq_investigations_open_owner_fingerprint", table_name="investigations")
    op.create_index(
        "uq_investigations_open_fingerprint",
        "investigations",
        ["fingerprint"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'running', 'completed', 'completed_degraded')"
        ),
    )
    for table in ("investigations", "alerts", "raw_webhooks"):
        op.drop_index(f"ix_{table}_owner_user_id", table_name=table)
        op.drop_column(table, "owner_user_id")
