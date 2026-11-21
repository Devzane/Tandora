"""Approval SQLAlchemy Model."""

from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("drafts.id", ondelete="CASCADE"), unique=True, nullable=False)
    outreach_thread_id: Mapped[int] = mapped_column(Integer, ForeignKey("outreach_threads.id", ondelete="CASCADE"), nullable=False)
    approved_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    body_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    draft = relationship("Draft", back_populates="approval")
    thread = relationship("OutreachThread", back_populates="approvals")
    send_attempts = relationship("SendAttempt", back_populates="approval")
    events = relationship("OutreachEvent", back_populates="approval")
