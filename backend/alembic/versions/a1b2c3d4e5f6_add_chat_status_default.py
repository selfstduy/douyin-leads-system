"""add default value for leads.chat_status

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill existing NULL rows to 0
    op.execute("UPDATE leads SET chat_status = 0 WHERE chat_status IS NULL")
    # Add server default and set NOT NULL
    op.alter_column(
        "leads",
        "chat_status",
        existing_type=sa.Integer(),
        server_default="0",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "leads",
        "chat_status",
        existing_type=sa.Integer(),
        server_default=None,
        nullable=True,
    )
