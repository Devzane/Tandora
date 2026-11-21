---
name: sqlite-database
description: SQLite design, SQLAlchemy 2.x ORM, Alembic migrations, relationships, indexing, transactions, contact deduplication, and data integrity for Tandora.
risk: low
source: project
date_added: '2026-11-21'
---

# SQLite Database Skill — Tandora

## Purpose

This skill covers all database operations in Tandora: SQLAlchemy 2.x model definitions, Alembic migration management, 21-table schema enforcement, contact deduplication patterns, transaction management, and SQLite-specific optimization pragmas.

## When to Use

Read this skill before writing any SQLAlchemy model, Alembic migration, query helper, or transaction service.

## Required Engineering Practices

### 1. Engine Configuration & Pragmas

```python
# app/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False}
)

# Mandatory SQLite Pragmas on every connection
@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass
```

### 2. SQLAlchemy 2.x Model Patterns

#### Contact with Deduplication & Suppression Fields
```python
class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    headline: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    normalized_linkedin_url: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Deduplication flagging
    duplicate_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_of_contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    
    # Multi-level suppression
    suppressed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suppressed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="contacts")
    email_addresses = relationship("EmailAddress", back_populates="contact", cascade="all, delete-orphan")
    phone_numbers = relationship("PhoneNumber", back_populates="contact", cascade="all, delete-orphan")
    roles = relationship("ContactRole", back_populates="contact", cascade="all, delete-orphan")
```

#### Approval with SHA-256 Content Hash
```python
class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), unique=True, nullable=False)
    outreach_thread_id: Mapped[int] = mapped_column(ForeignKey("outreach_threads.id"), nullable=False)
    approved_content_hash: Mapped[str] = mapped_column(String, nullable=False)
    recipient_address: Mapped[str] = mapped_column(String, nullable=False)
    subject_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    body_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
```

#### Persistent Send Attempt State Machine
```python
class SendAttempt(Base):
    __tablename__ = "send_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outreach_thread_id: Mapped[int] = mapped_column(ForeignKey("outreach_threads.id"), nullable=False)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), nullable=False)
    approval_id: Mapped[int] = mapped_column(ForeignKey("approvals.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending, sending, sent, failed, unknown
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recipient_address: Mapped[str] = mapped_column(String, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    smtp_response: Mapped[str | None] = mapped_column(String, nullable=True)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

### 3. Contact Deduplication Queries

```python
from sqlalchemy import select, func
from urllib.parse import urlparse, urlunparse

def normalize_linkedin_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    parsed = urlparse(raw_url.strip())
    # Standardize hostname and strip query/fragment/trailing slash
    netloc = "www.linkedin.com"
    path = parsed.path.rstrip("/")
    return urlunparse(("https", netloc, path, "", "", "")).lower()

def find_or_deduplicate_contact(
    db: Session,
    normalized_linkedin: str | None,
    email: str | None,
    first_name: str,
    last_name: str | None,
    company_id: int | None
) -> tuple[Contact | None, bool]:
    """
    Returns (contact, is_candidate_flagged).
    """
    # 1. Primary match on normalized LinkedIn URL
    if normalized_linkedin:
        existing = db.scalar(select(Contact).where(Contact.normalized_linkedin_url == normalized_linkedin))
        if existing:
            return existing, False

    # 2. Secondary match on normalized Email Address
    if email:
        clean_email = email.strip().lower()
        addr_match = db.scalar(select(EmailAddress).where(EmailAddress.address == clean_email))
        if addr_match:
            return db.get(Contact, addr_match.contact_id), False

    # 3. Tertiary cautious match: Name + Company
    if company_id and first_name and last_name:
        candidate = db.scalar(
            select(Contact).where(
                Contact.company_id == company_id,
                func.lower(Contact.first_name) == first_name.strip().lower(),
                func.lower(Contact.last_name) == last_name.strip().lower()
            )
        )
        if candidate:
            # Do NOT auto-merge. Flag as candidate duplicate for review.
            return candidate, True

    return None, False
```

### 4. Transactions & Atomic Commits
Use `db.begin()` or context manager blocks when orchestrating multi-entity captures (e.g. creating Capture + Post + Contact + Email + Phone + Opportunity atomically):

```python
def persist_capture_bundle(db: Session, payload: CapturePayload) -> Capture:
    with db.begin():
        capture = Capture(...)
        db.add(capture)
        # Deduplicate and attach entities...
        write_audit_log(db, "prospect_captured", ...)
        return capture
```

---

## Testing Requirements

- Use an in-memory SQLite engine (`sqlite:///:memory:`) for tests.
- Always attach the `PRAGMA foreign_keys = ON;` connection listener in test fixtures.
- Test that duplicate normalized LinkedIn URLs raise `IntegrityError` or resolve via deduplication service.
- Test that duplicate idempotency keys on `send_attempts` are blocked.
