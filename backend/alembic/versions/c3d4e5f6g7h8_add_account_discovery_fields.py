"""add monitor_accounts source/last_high_intent_at/total_high_count columns

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-08-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "c3d4e5f6g7h8"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitor_accounts",
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
    )
    op.add_column(
        "monitor_accounts",
        sa.Column("last_high_intent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "monitor_accounts",
        sa.Column("total_high_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_monitor_accounts_source", "monitor_accounts", ["source"])


def downgrade() -> None:
    op.drop_index("ix_monitor_accounts_source", table_name="monitor_accounts")
    op.drop_column("monitor_accounts", "total_high_count")
    op.drop_column("monitor_accounts", "last_high_intent_at")
    op.drop_column("monitor_accounts", "source")
