---
name: security-engineering
description: Secrets management, API security, input validation, access control, privacy, secure logging, and email outreach safeguards for Tandora.
risk: low
source: project
date_added: '2026-11-21'
---

# Security Engineering Skill — Tandora

## Purpose

This skill covers all security engineering standards for Tandora: credential management, API security, input validation, audit logging, suppression enforcement, and outbound outreach safeguards.

## When to Use

Read this skill before implementing authentication, credential loading, audit logging, suppression logic, or sending safeguards.

## Required Engineering Practices

### Credential Management

Configuration is loaded from environment variables using `python-dotenv`:

```python
# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Core app settings
    database_path: str = "./data/tandora.db"
    daily_sending_limit: int = 20
    llm_provider: str = "gemini"
    extension_api_secret: str = ""

    # External integration credentials (validated lazily on-demand)
    gemini_api_key: str | None = None
    reoon_api_key: str | None = None
    zoho_smtp_username: str | None = None
    zoho_smtp_password: str | None = None
    zoho_imap_username: str | None = None
    zoho_imap_password: str | None = None
    google_credentials_path: str | None = None
    google_sheets_id: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

Each integration validates its required credentials on-demand upon invocation:
```python
def require_reoon_api_key() -> str:
    key = get_settings().reoon_api_key
    if not key:
        raise ValueError("REOON_API_KEY environment variable is not configured. Please set it in .env to use email verification.")
    return key
```
This ensures unconfigured external services do not prevent application startup or block unrelated features.

### Extension API Authentication

```python
# app/dependencies/auth.py
from fastapi import Header, HTTPException
from app.config import get_settings

async def require_extension_secret(
    x_extension_secret: str = Header(..., alias="X-Extension-Secret")
) -> None:
    if x_extension_secret != get_settings().extension_api_secret:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_secret", "message": "Extension secret is missing or invalid"}
        )
```

Apply to protected capture routes:
```python
@router.post("/captures", dependencies=[Depends(require_extension_secret)])
def create_capture(...):
    ...
```

### Input Validation & Sanitization

```python
from pydantic import BaseModel, EmailStr, field_validator

class EmailAddressCreate(BaseModel):
    address: EmailStr
    source: str | None = None
    is_primary: bool = False

class ContactCreate(BaseModel):
    first_name: str
    last_name: str | None = None
    linkedin_url: str | None = None

    @field_validator("first_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("first_name cannot be empty")
        return cleaned

    @field_validator("linkedin_url")
    @classmethod
    def valid_linkedin_url(cls, v: str | None) -> str | None:
        if v and not v.startswith("https://www.linkedin.com/"):
            raise ValueError("LinkedIn URL must start with https://www.linkedin.com/")
        return v
```

### Suppression Enforcement

```python
def check_suppression(db: Session, contact_id: int, thread_id: int | None = None) -> None:
    contact = db.get(Contact, contact_id)
    if contact and contact.suppressed:
        raise ContactSuppressedException(
            f"Contact {contact_id} is suppressed: {contact.suppressed_reason}"
        )
    
    if thread_id:
        thread = db.get(OutreachThread, thread_id)
        if thread and thread.status == "suppressed":
            raise ContactSuppressedException(
                f"Outreach thread {thread_id} is suppressed"
            )

class ContactSuppressedException(Exception):
    pass
```

### Audit Log Writer

The audit log is append-only. Never perform UPDATE or DELETE on `audit_log`:

```python
# app/services/audit_service.py
import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

def write_audit_log(
    db: Session,
    event_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str = "",
    metadata: dict | None = None
) -> None:
    entry = AuditLog(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        metadata=json.dumps(metadata or {}),
        created_at=datetime.utcnow()
    )
    db.add(entry)
    logger.info("AUDIT: %s | %s:%s | %s", event_type, entity_type, entity_id, description)
```

### Safe Send Guard

`safe_send` is the single authorized pathway for dispatching emails:

```python
def safe_send(
    db: Session,
    thread_id: int,
    draft_id: int,
    approval_id: int
) -> str:
    # 1. Enforce all 10 pre-send safety checks against persistent DB records
    pre_send_checks(db, thread_id, draft_id, approval_id)

    thread = db.get(OutreachThread, thread_id)
    draft = db.get(Draft, draft_id)
    email_addr = db.get(EmailAddress, thread.selected_email_address_id)

    thread_msg_id = get_thread_message_id(db, thread_id) if draft.draft_type == "followup" else None

    # 2. Dispatch
    client = ZohoSMTPClient()
    message_id = client.send(
        to_address=email_addr.address,
        subject=draft.subject,
        body=draft.body,
        thread_message_id=thread_msg_id
    )

    # 3. Record sent event
    event = OutreachEvent(
        outreach_thread_id=thread_id,
        draft_id=draft_id,
        approval_id=approval_id,
        event_type=draft.draft_type,
        sent_at=datetime.utcnow(),
        message_id=message_id,
        recipient_address=email_addr.address
    )
    db.add(event)

    write_audit_log(
        db, "email_sent", "outreach_thread", thread_id,
        f"Email sent to {email_addr.address}", {"message_id": message_id}
    )
    return message_id
```

## Common Mistakes

- Placing the extension secret in plaintext client scripts instead of `chrome.storage.local`.
- Falling back silently when security/pre-send checks fail.
- Allowing update/delete endpoints on `audit_log`.
- Overlooking suppression checks during follow-up dispatch.

## Security Considerations

- FastAPI backend binds exclusively to `127.0.0.1` (never `0.0.0.0`).
- The `.env` file must be git-ignored.
- All secrets are injected through environment variables.
- Audit logging records every critical transition (creation, verification, draft, approval, sending, pause, suppression).

## Project-Specific Constraints

- Single user local deployment on Windows 11.
- No commercial auth/multi-tenant overhead.
- Safe sending controls strictly adhered to without exception.
