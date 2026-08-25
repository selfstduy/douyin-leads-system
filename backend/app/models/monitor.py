import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MonitorAccount(Base):
    __tablename__ = "monitor_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    douyin_url: Mapped[str] = mapped_column(String(512), nullable=False)
    douyin_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    avatar: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active / paused / error / removed
    poll_interval_min: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 账号来源与质量追踪
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual / discovered
    last_high_intent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_high_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    videos = relationship("Video", back_populates="monitor_account", lazy="selectin")


class DouyinChatAccount(Base):
    __tablename__ = "douyin_chat_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    douyin_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    cookie_data: Mapped[str] = mapped_column(Text, default="", nullable=False)
    login_status: Mapped[str] = mapped_column(String(20), default="offline", nullable=False)  # online / offline / expired
    assigned_to_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    last_active_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
