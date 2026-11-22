"""Add user-managed integration credentials and delivery settings."""

from alembic import op
import sqlalchemy as sa


revision = "0014_integrations"
down_revision = "0013_account_display_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_user_id", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("webhook_url_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("webhook_url_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "provider", name="uq_integrations_owner_provider"),
    )
    op.create_index("ix_integrations_owner_user_id", "integrations", ["owner_user_id"])
    op.create_index(
        "ix_integrations_owner_provider_enabled",
        "integrations",
        ["owner_user_id", "provider", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_integrations_owner_provider_enabled", table_name="integrations")
    op.drop_index("ix_integrations_owner_user_id", table_name="integrations")
    op.drop_table("integrations")
