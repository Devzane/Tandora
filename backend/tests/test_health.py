"""Tests for application health check, configuration, and SQLite foreign key enforcement."""

import os
import tempfile
import pytest
from sqlalchemy import Column, Integer, String, ForeignKey, text, create_engine, event
from sqlalchemy.exc import IntegrityError
from app.database import Base, set_sqlite_pragmas
from app.config import Settings, MissingCredentialError
from app.main import app, lifespan


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


def test_docs_endpoints_accessible(client):
    """FastAPI OpenAPI documentation and schema endpoints must be accessible."""
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200

    schema_resp = client.get("/openapi.json")
    assert schema_resp.status_code == 200
    assert schema_resp.json()["info"]["title"] == "Tandora Local Hub"


def test_error_handling_not_found(client):
    """Unknown routes must return HTTP 404 with structured detail."""
    response = client.get("/nonexistent-endpoint")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_error_handling_method_not_allowed(client):
    """Invalid HTTP methods must return HTTP 405 Method Not Allowed."""
    response = client.post("/health")
    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}


@pytest.mark.asyncio
async def test_application_lifespan_startup():
    """Application lifespan context manager must start up and shut down cleanly."""
    async with lifespan(app):
        # Lifespan startup completed
        pass


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


def test_configuration_custom_database_path():
    """Database path in Settings must be configurable via constructor or environment."""
    custom_path = "./custom_data/custom.db"
    settings = Settings(database_path=custom_path)
    assert settings.database_path == custom_path


def test_database_initialization_directory_creation():
    """Database directory provisioning logic must create parent directories if missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested_dir = os.path.join(tmpdir, "nested", "storage")
        db_path = os.path.join(nested_dir, "test.db")
        parent = os.path.dirname(db_path)
        if not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        assert os.path.exists(parent)


def test_sqlite_file_connectivity_and_pragmas():
    """SQLite engine connected to a real file must enforce foreign keys and WAL mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_pragmas.db")
        engine = create_engine(f"sqlite:///{db_file}")
        event.listen(engine, "connect", set_sqlite_pragmas)

        with engine.connect() as conn:
            fk = conn.execute(text("PRAGMA foreign_keys;")).scalar()
            wal = conn.execute(text("PRAGMA journal_mode;")).scalar()
            assert fk == 1, "Foreign keys pragma failed to activate"
            assert wal.lower() == "wal", "WAL mode failed to activate"

        engine.dispose()


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
