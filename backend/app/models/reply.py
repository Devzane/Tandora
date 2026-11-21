"""Reply SQLAlchemy Model."""

from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_thread_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("outreach_threads.id", ondelete="SET NULL"), nullable=True, index=True)
    in_reply_to_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reply_message_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    sender_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    thread = relationship("OutreachThread", back_populates="replies")
