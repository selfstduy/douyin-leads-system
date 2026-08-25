import datetime

from sqlalchemy import String, Integer, DateTime, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiCallLog(Base):
    __tablename__ = "api_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # comment_api / video_api / llm_api / openkf_api
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    params: Mapped[str] = mapped_column(Text, default="", nullable=False)  # JSON string
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
