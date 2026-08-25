import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_accounts.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    publish_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_crawled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 生命周期管理字段
    heat_level: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)  # high / normal
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)  # active / paused / expired
    zero_comment_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 连续无新增评论次数
    last_poll_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 上次轮询时间
    last_comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 上次评论总数(用于判断是否有新增)

    monitor_account = relationship("MonitorAccount", back_populates="videos")
    comments = relationship("Comment", back_populates="video", lazy="selectin")
