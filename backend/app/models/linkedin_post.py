"""LinkedInPost SQLAlchemy Model."""

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class LinkedInPost(Base):
    __tablename__ = "linkedin_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capture_id: Mapped[int] = mapped_column(Integer, ForeignKey("captures.id", ondelete="CASCADE"), nullable=False)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_linkedin_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    author_headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    post_url: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    post_text: Mapped[str] = mapped_column(Text, nullable=False)
    post_timestamp: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_mentioned: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    capture = relationship("Capture", back_populates="posts")
    opportunity = relationship("Opportunity", back_populates="posts")
