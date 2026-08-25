"""add dm_queue table for private message send queue

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-08-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "d4e5f6g7h8i9"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dm_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("user_uid", sa.String(128), nullable=False),
        sa.Column("original_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("send_account_id", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dm_queue_lead_id", "dm_queue", ["lead_id"])
    op.create_index("ix_dm_queue_user_uid", "dm_queue", ["user_uid"])
    op.create_index("ix_dm_queue_status", "dm_queue", ["status"])
    op.create_index("ix_dm_queue_scheduled_date", "dm_queue", ["scheduled_date"])


def downgrade() -> None:
    op.drop_index("ix_dm_queue_scheduled_date", table_name="dm_queue")
    op.drop_index("ix_dm_queue_status", table_name="dm_queue")
    op.drop_index("ix_dm_queue_user_uid", table_name="dm_queue")
    op.drop_index("ix_dm_queue_lead_id", table_name="dm_queue")
    op.drop_table("dm_queue")
