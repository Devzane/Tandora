"""SheetsSyncState SQLAlchemy Model."""

from datetime import datetime
from sqlalchemy import Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SheetsSyncState(Base):
    __tablename__ = "sheets_sync_state"
    __table_args__ = (
        UniqueConstraint("entity_type", "sheets_id", "sheet_name", name="uq_sheets_sync_entity_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'company', 'contact', 'opportunity', 'outreach'
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sheets_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sync_checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
