import datetime

from sqlalchemy import String, Integer, DateTime, Date, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DmQueue(Base):
    """私信发送队列 — high意向线索入队后由限流调度系统统一发送。"""

    __tablename__ = "dm_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_uid: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    original_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 评论时间越新优先级越高
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # pending / sent / failed / skipped / overflow
    scheduled_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, index=True
    )  # 计划发送日期(当日溢出→次日)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    send_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
