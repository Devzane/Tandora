"""SendAttempt SQLAlchemy Model."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SendAttempt(Base):
    __tablename__ = "send_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_thread_id: Mapped[int] = mapped_column(Integer, ForeignKey("outreach_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    approval_id: Mapped[int] = mapped_column(Integer, ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recipient_address: Mapped[str] = mapped_column(String(255), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    thread = relationship("OutreachThread", back_populates="send_attempts")
    draft = relationship("Draft", back_populates="send_attempts")
    approval = relationship("Approval", back_populates="send_attempts")
    event = relationship("OutreachEvent", back_populates="send_attempt", uselist=False)
