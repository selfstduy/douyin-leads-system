"""add leads.chat_id column

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("chat_id", sa.String(128), nullable=True),
    )
    op.create_index("ix_leads_chat_id", "leads", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_chat_id", table_name="leads")
    op.drop_column("leads", "chat_id")
