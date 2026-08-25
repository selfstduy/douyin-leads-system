"""add video lifecycle management fields

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
    # heat_level: 热度等级 high/normal
    op.add_column(
        "videos",
        sa.Column("heat_level", sa.String(20), server_default="normal", nullable=False),
    )

    # status: 视频状态 active/paused/expired
    op.add_column(
        "videos",
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
    )
    op.create_index("ix_videos_status", "videos", ["status"])

    # zero_comment_streak: 连续无新增评论次数
    op.add_column(
        "videos",
        sa.Column("zero_comment_streak", sa.Integer(), server_default="0", nullable=False),
    )

    # last_poll_time: 上次轮询时间
    op.add_column(
        "videos",
        sa.Column("last_poll_time", sa.DateTime(timezone=True), nullable=True),
    )

    # last_comment_count: 上次评论总数
    op.add_column(
        "videos",
        sa.Column("last_comment_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("videos", "last_comment_count")
    op.drop_column("videos", "last_poll_time")
    op.drop_column("videos", "zero_comment_streak")
    op.drop_index("ix_videos_status", table_name="videos")
    op.drop_column("videos", "status")
    op.drop_column("videos", "heat_level")
