import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(Integer, ForeignKey("comments.id"), nullable=False)
    video_id: Mapped[int] = mapped_column(Integer, ForeignKey("videos.id"), nullable=False)
    user_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    user_nickname: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    user_avatar: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    intent_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)  # high / medium / low
    ai_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending / assigned / following / converted / closed
    chat_status: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # 0=待处理, 1=人工服务, 2=AI托管
    chat_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)  # OpenKF external chat ID (e.g. "lead-123")
    round_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # AI对话轮次
    template_id: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)  # 使用的话术模板编号(1-3)
    assigned_to: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    followups = relationship("LeadFollowup", back_populates="lead", lazy="selectin")
    chat_messages = relationship("ChatMessage", back_populates="lead", lazy="selectin")


class LeadFollowup(Base):
    __tablename__ = "lead_followups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), nullable=False)
    operator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # note / status_change / assign
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lead = relationship("Lead", back_populates="followups")
