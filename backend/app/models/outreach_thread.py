"""OutreachThread SQLAlchemy Model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OutreachThread(Base):
    __tablename__ = "outreach_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    opportunity_id: Mapped[int] = mapped_column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_email_address_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_addresses.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("opportunity_id", "contact_id", name="uq_outreach_threads_opp_contact"),
    )

    opportunity = relationship("Opportunity", back_populates="threads")
    contact = relationship("Contact", back_populates="threads")
    selected_email_address = relationship("EmailAddress", back_populates="threads")
    drafts = relationship("Draft", back_populates="thread", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="thread", cascade="all, delete-orphan")
    send_attempts = relationship("SendAttempt", back_populates="thread", cascade="all, delete-orphan")
    events = relationship("OutreachEvent", back_populates="thread", cascade="all, delete-orphan")
    followup_schedules = relationship("FollowupSchedule", back_populates="thread", cascade="all, delete-orphan")
    replies = relationship("Reply", back_populates="thread", cascade="all, delete-orphan")
