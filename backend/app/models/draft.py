"""Draft SQLAlchemy Model."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_thread_id: Mapped[int] = mapped_column(Integer, ForeignKey("outreach_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_type: Mapped[str] = mapped_column(String(50), nullable=False)
    followup_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_edited: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("outreach_thread_id", "draft_type", "followup_number", "version", name="uq_drafts_thread_version"),
    )

    thread = relationship("OutreachThread", back_populates="drafts")
    approval = relationship("Approval", back_populates="draft", uselist=False, cascade="all, delete-orphan")
    send_attempts = relationship("SendAttempt", back_populates="draft")
    events = relationship("OutreachEvent", back_populates="draft")
