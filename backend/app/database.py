"""Database engine, session management, SQLite connection listeners, and security triggers."""

import os
from collections.abc import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from app.config import get_settings


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


settings = get_settings()

# Ensure parent directory for database file exists
db_dir = os.path.dirname(settings.database_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# Format SQLite connection URL
db_url = f"sqlite:///{settings.database_path}"

engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False}
)


def ensure_audit_log_triggers(connection_or_cursor):
    """Create authoritative SQLite triggers preventing UPDATE and DELETE on audit_log."""
    sql_update = """
    CREATE TRIGGER IF NOT EXISTS prevent_audit_log_update
    BEFORE UPDATE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'Audit log records are immutable and cannot be updated.');
    END;
    """
    sql_delete = """
    CREATE TRIGGER IF NOT EXISTS prevent_audit_log_delete
    BEFORE DELETE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'Audit log records are immutable and cannot be deleted.');
    END;
    """
    if hasattr(connection_or_cursor, "execute"):
        try:
            # Check if audit_log table exists
            if hasattr(connection_or_cursor, "cursor"):
                # Connection object
                cur = connection_or_cursor.cursor()
                cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_log';")
                if cur.fetchone():
                    cur.execute(sql_update)
                    cur.execute(sql_delete)
                cur.close()
            else:
                # Cursor object
                connection_or_cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_log';")
                if connection_or_cursor.fetchone():
                    connection_or_cursor.execute(sql_update)
                    connection_or_cursor.execute(sql_delete)
        except Exception:
            pass


@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    """Mandatory SQLite Pragmas: enforce foreign keys, Write-Ahead Logging, and audit log immutability."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA journal_mode=WAL;")
    ensure_audit_log_triggers(cursor)
    cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
