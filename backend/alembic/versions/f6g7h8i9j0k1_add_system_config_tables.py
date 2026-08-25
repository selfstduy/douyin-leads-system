"""add system_configs and config_change_logs tables

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-08-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "f6g7h8i9j0k1"
down_revision = "e5f6g7h8i9j0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── system_configs 表 ──
    op.create_table(
        "system_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("value_type", sa.String(16), nullable=False, server_default="str"),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("label", sa.String(128), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_system_configs_key"),
    )
    op.create_index("ix_system_configs_key", "system_configs", ["key"], unique=True)
    op.create_index("ix_system_configs_category", "system_configs", ["category"])

    # ── config_change_logs 表 ──
    op.create_table(
        "config_change_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("config_key", sa.String(128), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("new_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("changed_by", sa.String(64), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_config_change_logs_config_key", "config_change_logs", ["config_key"])


def downgrade() -> None:
    op.drop_index("ix_config_change_logs_config_key", table_name="config_change_logs")
    op.drop_table("config_change_logs")
    op.drop_index("ix_system_configs_category", table_name="system_configs")
    op.drop_index("ix_system_configs_key", table_name="system_configs")
    op.drop_table("system_configs")
