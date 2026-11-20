"""Add editable display names to local accounts."""

from alembic import op
import sqlalchemy as sa


revision = "0013_account_display_name"
down_revision = "0012_user_secrets_and_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_accounts", sa.Column("display_name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_accounts", "display_name")
