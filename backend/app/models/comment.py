import datetime

from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("videos.id"), nullable=True)
    comment_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    user_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    user_nickname: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    comment_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    crawled_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), default="account", nullable=False)  # account / topic
    source_topic_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("topic_monitors.id"), nullable=True)

    video = relationship("Video", back_populates="comments")
