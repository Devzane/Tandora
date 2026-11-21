"""Capture SQLAlchemy Model."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Capture(Base):
    __tablename__ = "captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capture_type: Mapped[str] = mapped_column(String(50), nullable=False)
    page_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    posts = relationship("LinkedInPost", back_populates="capture")
