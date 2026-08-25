import datetime

from sqlalchemy import Integer, Date, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyStat(Base):
    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    total_comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_intent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    medium_intent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    converted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
