---
name: sqlite-database
description: SQLite design, SQLAlchemy 2.x ORM, Alembic migrations, relationships, indexing, transactions, and data integrity for Tandora.
risk: low
source: project
date_added: '2026-11-21'
---

# SQLite Database Skill — Tandora

## Purpose

This skill covers all database work in Tandora: SQLAlchemy model definitions, Alembic migration management, query patterns, transaction handling, and data integrity enforcement.

## When to Use

Read this skill before writing any SQLAlchemy model, Alembic migration, database query, or service function that accesses the database.

## Required Engineering Practices

### Engine Configuration

```python
# app/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False}
)

# CRITICAL: Enable foreign keys on every connection
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass
```

### SQLAlchemy 2.x Model Pattern

```python
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.database import Base

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="employer")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    opportunities: Mapped[list["Opportunity"]] = relationship("Opportunity", back_populates="company")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="company")

    __table_args__ = (
        Index("idx_companies_name", "name"),
    )
```

### Alembic Migration Workflow

1. After modifying a model, create a migration:
   ```
   alembic revision --autogenerate -m "describe_the_change"
   ```
2. Review the generated migration file. Never commit an auto-generated migration without reviewing it.
3. Apply the migration:
   ```
   alembic upgrade head
   ```
4. Never modify the database schema manually (outside of Alembic).
5. Never delete migration files. The history is permanent.

### Query Patterns (SQLAlchemy 2.x Style)

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

# Fetch by ID
def get_company(db: Session, company_id: int) -> Company | None:
    return db.scalar(select(Company).where(Company.id == company_id))

# Fetch with filter
def list_companies(db: Session, type: str | None = None) -> list[Company]:
    stmt = select(Company)
    if type:
        stmt = stmt.where(Company.type == type)
    return list(db.scalars(stmt).all())

# Insert
def create_company(db: Session, name: str, type: str) -> Company:
    company = Company(external_id=str(uuid4()), name=name, type=type)
    db.add(company)
    db.flush()  # Get the ID without committing
    return company
```

### Transaction Management

```python
# In service layer — use transactions for multi-step operations
def create_opportunity_with_company(db: Session, ...) -> Opportunity:
    with db.begin():
        company = get_or_create_company(db, company_name)
        opportunity = create_opportunity(db, company.id, ...)
        write_audit_log(db, "opportunity_captured", ...)
        return opportunity
```

### Relationships

- Use `relationship()` with `back_populates` for bidirectional navigation.
- Use `lazy="select"` (default) for most relationships.
- Avoid N+1 queries: use `joinedload()` when fetching collections.

```python
from sqlalchemy.orm import joinedload

contacts_with_emails = db.scalars(
    select(Contact)
    .options(joinedload(Contact.email_addresses))
    .where(Contact.company_id == company_id)
).unique().all()
```

## Common Mistakes

- Forgetting `PRAGMA foreign_keys = ON`. → SQLite ignores FK constraints without it.
- Using `session.commit()` inside service functions called from routers. → Let the router's dependency handle commit/rollback.
- Using synchronous SQLite with async FastAPI without proper configuration. → Use `check_same_thread=False` and synchronous sessions, or use `aiosqlite` for full async.
- Running `alembic autogenerate` without reviewing the output. → Always review before applying.
- Hardcoding database paths. → Use `settings.database_path` from config.

## Security Considerations

- Database file must be stored in a user-accessible location, not in the project root that might be version-controlled.
- Never construct SQL strings with user-supplied data. Always use parameterized queries via SQLAlchemy.
- The audit log table must never have UPDATE or DELETE granted to the application session.

## Testing Requirements

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    # Enable foreign keys
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    Base.metadata.drop_all(engine)
```

- Use in-memory SQLite for all unit tests.
- Test unique constraints by attempting duplicate inserts and asserting `IntegrityError`.
- Test foreign key constraints by attempting orphaned inserts.
- Test that migrations apply cleanly to an empty database.

## Project-Specific Constraints

- Database: SQLite only. No PostgreSQL, MySQL, or any hosted database.
- `external_id` columns use UUID4 strings as stable identifiers for Sheets sync.
- The `audit_log` table is INSERT-only from the application layer.
- All timestamps stored as UTC datetime objects.
- `PRAGMA foreign_keys = ON` is mandatory on every connection.
