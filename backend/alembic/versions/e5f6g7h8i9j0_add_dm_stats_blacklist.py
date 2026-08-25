"""add dm_daily_stats and user_blacklist tables

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-08-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "e5f6g7h8i9j0"
down_revision = "d4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── dm_daily_stats 表 ──
    op.create_table(
        "dm_daily_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("read_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reply_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wechat_added_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uq_dm_daily_stats_date"),
    )
    op.create_index("ix_dm_daily_stats_date", "dm_daily_stats", ["date"])

    # ── user_blacklist 表 ──
    op.create_table(
        "user_blacklist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_uid", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_uid", name="uq_user_blacklist_user_uid"),
    )
    op.create_index("ix_user_blacklist_user_uid", "user_blacklist", ["user_uid"])


def downgrade() -> None:
    op.drop_index("ix_user_blacklist_user_uid", table_name="user_blacklist")
    op.drop_table("user_blacklist")
    op.drop_index("ix_dm_daily_stats_date", table_name="dm_daily_stats")
    op.drop_table("dm_daily_stats")
