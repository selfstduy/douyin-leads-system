"""add alerts and api_call_logs tables

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
    # ── alerts 表 ──
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_level", "alerts", ["level"])
    op.create_index("ix_alerts_source", "alerts", ["source"])

    # ── api_call_logs 表 ──
    op.create_table(
        "api_call_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_type", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("params", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_call_logs_api_type", "api_call_logs", ["api_type"])
    op.create_index("ix_api_call_logs_created_at", "api_call_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_api_call_logs_created_at", table_name="api_call_logs")
    op.drop_index("ix_api_call_logs_api_type", table_name="api_call_logs")
    op.drop_table("api_call_logs")
    op.drop_index("ix_alerts_source", table_name="alerts")
    op.drop_index("ix_alerts_level", table_name="alerts")
    op.drop_table("alerts")
