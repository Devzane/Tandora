"""Contact SQLAlchemy Model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    normalized_linkedin_url: Mapped[str | None] = mapped_column(String(500), unique=True, nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    duplicate_of_contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    suppressed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    suppressed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    sheets_row_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sheets_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    company = relationship("Company", back_populates="contacts")
    roles = relationship("ContactRole", back_populates="contact", cascade="all, delete-orphan")
    emails = relationship("EmailAddress", back_populates="contact", cascade="all, delete-orphan")
    phones = relationship("PhoneNumber", back_populates="contact", cascade="all, delete-orphan")
    opportunity_contacts = relationship("OpportunityContact", back_populates="contact", cascade="all, delete-orphan")
    threads = relationship("OutreachThread", back_populates="contact")
