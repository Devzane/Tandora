"""Tests verifying the immutable, append-only nature of the audit_log table."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from app.models.audit_log import AuditLog
from app.services.audit_service import write_audit_log


def test_audit_log_append_succeeds(test_db):
    """Verify write_audit_log inserts new audit records successfully."""
    entry = write_audit_log(
        test_db,
        event_type="test_event",
        description="Initial audit log entry",
        entity_type="contact",
        entity_id=1,
        metadata={"user": "admin", "action": "test"},
    )
    test_db.commit()

    assert entry.id is not None
    fetched = test_db.get(AuditLog, entry.id)
    assert fetched.event_type == "test_event"
    assert fetched.description == "Initial audit log entry"


def test_audit_log_update_prevented_by_trigger(test_db):
    """Verify attempting to UPDATE an audit_log record is rejected by database trigger."""
    entry = write_audit_log(
        test_db,
        event_type="tamper_check",
        description="Original description",
    )
    test_db.commit()

    # Attempt ORM-level update
    entry.description = "Altered description"
    with pytest.raises((IntegrityError, OperationalError)):
        test_db.commit()

    test_db.rollback()

    # Attempt raw SQL update
    with pytest.raises((IntegrityError, OperationalError)):
        test_db.execute(
            text("UPDATE audit_log SET description = 'Tampered' WHERE id = :id"),
            {"id": entry.id},
        )
        test_db.commit()

    test_db.rollback()

    # Verify record remained original
    refreshed = test_db.get(AuditLog, entry.id)
    assert refreshed.description == "Original description"


def test_audit_log_delete_prevented_by_trigger(test_db):
    """Verify attempting to DELETE an audit_log record is rejected by database trigger."""
    entry = write_audit_log(
        test_db,
        event_type="delete_check",
        description="Entry slated for deletion",
    )
    test_db.commit()

    # Attempt ORM-level delete
    test_db.delete(entry)
    with pytest.raises((IntegrityError, OperationalError)):
        test_db.commit()

    test_db.rollback()

    # Attempt raw SQL delete
    with pytest.raises((IntegrityError, OperationalError)):
        test_db.execute(
            text("DELETE FROM audit_log WHERE id = :id"),
            {"id": entry.id},
        )
        test_db.commit()

    test_db.rollback()

    # Verify record still exists
    refreshed = test_db.get(AuditLog, entry.id)
    assert refreshed is not None
    assert refreshed.description == "Entry slated for deletion"
