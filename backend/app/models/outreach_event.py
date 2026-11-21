"""OutreachEvent SQLAlchemy Model."""

from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OutreachEvent(Base):
    __tablename__ = "outreach_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_thread_id: Mapped[int] = mapped_column(Integer, ForeignKey("outreach_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    approval_id: Mapped[int] = mapped_column(Integer, ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False)
    send_attempt_id: Mapped[int] = mapped_column(Integer, ForeignKey("send_attempts.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    followup_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    message_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    recipient_address: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    thread = relationship("OutreachThread", back_populates="events")
    draft = relationship("Draft", back_populates="events")
    approval = relationship("Approval", back_populates="events")
    send_attempt = relationship("SendAttempt", back_populates="event")
    bounces = relationship("Bounce", back_populates="outreach_event")
