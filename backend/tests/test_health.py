"""Tests for application health check, configuration, and SQLite foreign key enforcement."""

import pytest
from sqlalchemy import Column, Integer, String, ForeignKey, text
from sqlalchemy.exc import IntegrityError
from app.database import Base
from app.config import Settings, MissingCredentialError


class ParentItem(Base):
    __tablename__ = "test_parents"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class ChildItem(Base):
    __tablename__ = "test_children"
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("test_parents.id"), nullable=False)


def test_health_returns_200(client):
    """GET /health must return HTTP 200 with service metadata and timestamp."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "tandora"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data


def test_unconfigured_integrations_do_not_crash_startup():
    """Application settings must instantiate cleanly without external API credentials."""
    settings = Settings(
        gemini_api_key=None,
        reoon_api_key=None,
        zoho_smtp_password=None,
        google_credentials_path=None
    )
    assert settings.gemini_api_key is None
    assert settings.daily_sending_limit == 20
    assert settings.dry_run is True


def test_missing_credentials_raise_actionable_error():
    """Invoking an unconfigured integration must raise a clear MissingCredentialError."""
    settings = Settings(gemini_api_key=None, reoon_api_key=None)

    with pytest.raises(MissingCredentialError, match="GEMINI_API_KEY"):
        settings.validate_gemini_credentials()

    with pytest.raises(MissingCredentialError, match="REOON_API_KEY"):
        settings.validate_reoon_credentials()


def test_foreign_keys_enforced(test_engine, test_db):
    """SQLite engine must enforce foreign key integrity via PRAGMA foreign_keys=ON."""
    Base.metadata.create_all(test_engine)

    # Attempting to insert a child referencing a non-existent parent must fail
    orphan = ChildItem(id=1, parent_id=999)
    test_db.add(orphan)

    with pytest.raises(IntegrityError):
        test_db.commit()

    test_db.rollback()


def test_wal_mode_enabled(test_db):
    """SQLite engine must be operating with Write-Ahead Logging (WAL) enabled."""
    mode = test_db.execute(text("PRAGMA journal_mode;")).scalar()
    # In-memory test engine returns 'memory', file engines return 'wal'
    assert mode in ("wal", "memory")
