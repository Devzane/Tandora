"""EmailVerification SQLAlchemy Model."""

from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_address_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_addresses.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    catch_all_approved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catch_all_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reoon_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    email_address = relationship("EmailAddress", back_populates="verifications")
