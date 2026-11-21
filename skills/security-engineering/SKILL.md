---
name: security-engineering
description: Secrets management, API security, input validation, SHA-256 approval hashing, send-attempt lifecycle, multi-level suppression, and outreach compliance safeguards for Tandora.
risk: low
source: project
date_added: '2026-11-21'
---

# Security Engineering Skill — Tandora

## Purpose

This skill covers all security engineering standards for Tandora: credential management, API security, SHA-256 approval hashing, the persistent send-attempt lifecycle, multi-level suppression enforcement, and outbound compliance safeguards.

## When to Use

Read this skill before implementing authentication, credential handling, approval logic, outbound delivery guards, suppression systems, or audit log writers.

## Required Engineering Practices

### 1. Secrets Management & On-Demand Validation

```python
# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_path: str = "./data/tandora.db"
    daily_sending_limit: int = 20
    llm_provider: str = "gemini"
    extension_api_secret: str = ""
    dry_run: bool = True  # Default to true for safety

    # External credentials (validated lazily on demand)
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

### 2. Approval Integrity & SHA-256 Content Hashing

An email may only be sent if its content is bit-for-bit identical to what the user explicitly approved.

```python
import hashlib

def calculate_approved_content_hash(
    recipient: str,
    subject: str,
    body: str,
    draft_id: int,
    version: int
) -> str:
    payload = f"{recipient.strip().lower()}\n{subject.strip()}\n{body.strip()}\n{draft_id}\n{version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def verify_approval_content_integrity(
    draft: Draft,
    recipient: str,
    approval: Approval
) -> bool:
    current_hash = calculate_approved_content_hash(
        recipient=recipient,
        subject=draft.subject,
        body=draft.body,
        draft_id=draft.id,
        version=draft.version
    )
    return current_hash == approval.approved_content_hash
```

### 3. Persistent Send-Attempt Lifecycle

SMTP and SQLite cannot participate in a shared two-phase distributed commit. Therefore, the send process must be staged persistently:

$$\text{Pre-Send Checks} \rightarrow \text{Persist 'pending'} \rightarrow \text{Commit DB} \rightarrow \text{Transition 'sending'} \rightarrow \text{Dispatch SMTP} \rightarrow \text{Commit 'sent'/'failed'/'unknown'}$$

```python
import asyncio

# Global delivery lock serializing all send operations
delivery_lock = asyncio.Lock()

async def execute_secure_send(
    db: Session,
    thread_id: int,
    draft_id: int,
    approval_id: int
) -> SendAttempt:
    async with delivery_lock:
        thread = db.get(OutreachThread, thread_id)
        draft = db.get(Draft, draft_id)
        approval = db.get(Approval, approval_id)
        email_addr = db.get(EmailAddress, thread.selected_email_address_id)
        
        # 1. Enforce all 10 pre-send checks
        pre_send_checks(db, thread_id, draft_id, approval_id)
        
        # 2. Verify SHA-256 content hash
        if not verify_approval_content_integrity(draft, email_addr.address, approval):
            raise PreSendCheckError("Draft content has changed since approval; re-approval required.")

        # 3. Create persistent SendAttempt in 'pending' state
        idempotency_key = hashlib.sha256(
            f"{thread_id}_{draft_id}_{approval_id}".encode()
        ).hexdigest()
        
        attempt = SendAttempt(
            outreach_thread_id=thread_id,
            draft_id=draft_id,
            approval_id=approval_id,
            idempotency_key=idempotency_key,
            status="pending",
            recipient_address=email_addr.address,
            dry_run=1 if get_settings().dry_run else 0
        )
        db.add(attempt)
        db.commit()  # CRITICAL: Commit before opening external socket

        # 4. Transition to 'sending'
        attempt.status = "sending"
        attempt.started_at = datetime.utcnow()
        db.commit()

        # 5. Dispatch
        if get_settings().dry_run:
            attempt.status = "sent"
            attempt.completed_at = datetime.utcnow()
            attempt.message_id = f"<dry-run-{idempotency_key[:12]}@local>"
            record_outreach_event(db, attempt)
            db.commit()
            return attempt

        try:
            client = ZohoSMTPClient()
            message_id = client.send(
                to_address=email_addr.address,
                subject=draft.subject,
                body=draft.body
            )
            attempt.status = "sent"
            attempt.message_id = message_id
            attempt.completed_at = datetime.utcnow()
            record_outreach_event(db, attempt)
            db.commit()
            return attempt
        except SMTPSendError as e:
            attempt.status = "failed"
            attempt.error_message = str(e)
            attempt.completed_at = datetime.utcnow()
            db.commit()
            raise
        except Exception as e:
            # Socket timeout or dropped connection: state is INDETERMINATE
            attempt.status = "unknown"
            attempt.error_message = f"Indeterminate state: {e}"
            attempt.completed_at = datetime.utcnow()
            db.commit()
            # NEVER auto-resend unknown attempts
            raise IndeterminateDeliveryError("SMTP connection dropped mid-flight; delivery state is unknown.") from e
```

### 4. 10 Mandatory Pre-Send Checks

```python
def pre_send_checks(db: Session, thread_id: int, draft_id: int, approval_id: int) -> None:
    config = get_app_config(db)
    thread = db.get(OutreachThread, thread_id)
    draft = db.get(Draft, draft_id)
    contact = db.get(Contact, thread.contact_id)
    email_addr = db.get(EmailAddress, thread.selected_email_address_id)
    company = db.get(Company, contact.company_id) if contact.company_id else None

    # 1. Approval exists
    approval = db.get(Approval, approval_id)
    if not approval or approval.draft_id != draft_id:
        raise PreSendCheckError("No valid approval record for this exact draft version")

    # 2. Global pause
    if config.get("sending_paused") == "true":
        raise PreSendCheckError("Global sending pause is active")

    # 3. Daily quota (< 20 sent today)
    today_sent = count_sent_today(db)
    limit = int(config.get("daily_sending_limit", "20"))
    if today_sent >= limit:
        raise PreSendCheckError(f"Daily quota of {limit} reached ({today_sent} sent today)")

    # 4. Contact suppression
    if contact.suppressed:
        raise PreSendCheckError(f"Contact is suppressed: {contact.suppressed_reason}")

    # 5. Address suppression
    if email_addr.suppressed:
        raise PreSendCheckError(f"Email address is suppressed: {email_addr.suppressed_reason}")
    if has_hard_bounce(db, email_addr.id):
        raise PreSendCheckError("Selected address has a recorded hard bounce")

    # 6. Organization suppression
    if company and company.suppressed:
        raise PreSendCheckError(f"Organization is suppressed: {company.suppressed_reason}")

    # 7. Verification eligibility
    usable, reason = is_address_usable(db, email_addr.id)
    if not usable:
        raise PreSendCheckError(f"Address verification ineligible: {reason}")

    # 8. Catch-all approval
    verification = get_latest_verification(db, email_addr.id)
    if verification and verification.status == "catch-all" and not verification.catch_all_approved:
        raise PreSendCheckError("Catch-all address requires separate explicit manual approval")

    # 9. Duplicate recipient check
    if has_already_sent_type(db, thread_id, draft.draft_type, draft.followup_number):
        raise PreSendCheckError("Message of this type has already been sent to this thread")

    # 10. Thread eligibility
    if thread.status in ("suppressed", "replied", "bounced", "closed"):
        raise PreSendCheckError(f"Outreach thread not eligible for sending (status: {thread.status})")
```

### 5. Multi-Level Suppression Rules
- **Contact-Level**: `contacts.suppressed = 1`. Blocks all outreach to this individual across all opportunities.
- **Address-Level**: `email_addresses.suppressed = 1`. Blocks sending to this specific address.
- **Organization-Level**: `companies.suppressed = 1`. Blocks outreach to all contacts employed by this organization.
- **Auto-Cancellation**: Suppressing an entity immediately updates all associated active `followup_schedules` to `status = 'cancelled'`.

### 6. Audit Logging Standard
- The `audit_log` table is append-only. No code path may issue `UPDATE` or `DELETE` statements on `audit_log`.

---

## Testing Requirements

- Test approval hash mismatch raises error and blocks send.
- Test that send-attempt record is committed before SMTP transmission.
- Test that unknown send attempts are flagged and never auto-retried.
- Test that delivery lock prevents concurrent duplicate sends.
- Test that dry-run mode simulates delivery without opening SMTP sockets.
