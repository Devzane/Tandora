"""Bounce SQLAlchemy Model."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Bounce(Base):
    __tablename__ = "bounces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_event_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("outreach_events.id", ondelete="SET NULL"), nullable=True)
    email_address_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("email_addresses.id", ondelete="SET NULL"), nullable=True, index=True)
    bounce_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'hard' or 'soft'
    bounce_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    outreach_event = relationship("OutreachEvent", back_populates="bounces")
    email_address = relationship("EmailAddress", back_populates="bounces")
