"""Audit Log Service — Append-Only Operational Trail."""

import json
from typing import Any
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    event_type: str,
    description: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an immutable append-only audit event in the database."""
    metadata_str = json.dumps(metadata) if metadata is not None else None
    log_entry = AuditLog(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        metadata_json=metadata_str,
    )
    db.add(log_entry)
    db.flush()
    return log_entry
