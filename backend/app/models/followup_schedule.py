"""FollowupSchedule SQLAlchemy Model."""

from datetime import datetime, date, timezone
from sqlalchemy import Integer, String, Text, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class FollowupSchedule(Base):
    __tablename__ = "followup_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_thread_id: Mapped[int] = mapped_column(Integer, ForeignKey("outreach_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    followup_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    suppressed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("outreach_thread_id", "followup_number", name="uq_followup_schedules_thread_number"),
    )

    thread = relationship("OutreachThread", back_populates="followup_schedules")
