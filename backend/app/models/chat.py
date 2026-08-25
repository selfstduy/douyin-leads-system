import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"), nullable=False)
    douyin_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("douyin_chat_accounts.id"), nullable=False)
    chat_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)  # OpenKF external chat ID
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound / outbound
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    msg_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text / image / video
    external_msg_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # OpenKF msg_id
    sent_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="sent", nullable=False)  # sent / delivered / failed

    lead = relationship("Lead", back_populates="chat_messages")
