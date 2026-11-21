"""OpportunityContact SQLAlchemy Model."""

from datetime import datetime, timezone
from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OpportunityContact(Base):
    __tablename__ = "opportunity_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("opportunity_id", "contact_id", name="uq_opportunity_contacts_opp_contact"),
    )

    opportunity = relationship("Opportunity", back_populates="opportunity_contacts")
    contact = relationship("Contact", back_populates="opportunity_contacts")
