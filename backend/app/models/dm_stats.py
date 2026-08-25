import datetime

from sqlalchemy import String, Integer, DateTime, Date, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DmDailyStats(Base):
    """私信每日统计 — 用于风控举报拉黑率计算。"""

    __tablename__ = "dm_daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # 发出条数
    read_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # 已读数
    reply_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # 回复数
    report_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # 举报数
    block_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # 拉黑数
    wechat_added_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # 加微数
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserBlacklist(Base):
    """用户黑名单 — 拒绝/举报/手动加入的用户不再发送私信。"""

    __tablename__ = "user_blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)  # 抖音用户UID
    reason: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)  # blacklisted_by_user/reported/manual
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
