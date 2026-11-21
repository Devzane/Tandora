---
name: email-delivery
description: Zoho SMTP and IMAP integration for Tandora — persistent send attempts, delivery locks, message threading, bounce handling, reply detection, 20/day quota, and dry-run sending.
risk: low
source: project
date_added: '2026-11-21'
---

# Email Delivery Skill — Tandora

## Purpose

This skill covers outbound email delivery via Zoho SMTP and inbound monitoring via Zoho IMAP: the persistent send-attempt lifecycle, delivery serialization lock, message threading, reply matching, hard bounce detection, rate limits, and dry-run execution.

## When to Use

Read this skill before implementing `integrations/zoho_smtp.py`, `integrations/zoho_imap.py`, `services/sending_service.py`, or `services/inbox_service.py`.

## Required Engineering Practices

### 1. Distributed Transaction Limitation
SMTP and SQLite cannot participate in a single two-phase distributed commit. If an application crashes or network connection drops after SMTP accepts an email but before the database commits, a duplicate-delivery risk exists.

To solve this, Tandora enforces a **persistent send-attempt lifecycle**:
$$\text{Pre-Send Checks} \rightarrow \text{Persist 'pending'} \rightarrow \text{Commit DB} \rightarrow \text{Transition 'sending'} \rightarrow \text{Dispatch SMTP} \rightarrow \text{Commit 'sent'/'failed'/'unknown'}$$

### 2. Zoho SMTP Client

```python
# app/integrations/zoho_smtp.py
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid, formatdate
from app.config import get_settings

logger = logging.getLogger(__name__)

ZOHO_SMTP_HOST = "smtp.zoho.com"
ZOHO_SMTP_PORT = 587  # STARTTLS

class ZohoSMTPClient:
    def __init__(self):
        settings = get_settings()
        self.username = settings.zoho_smtp_username
        self.password = settings.zoho_smtp_password
        if not self.username or not self.password:
            raise ValueError("Zoho SMTP credentials not configured in environment.")

    def send(self, to_address: str, subject: str, body: str,
             thread_message_id: str | None = None) -> str:
        """
        Send an email via Zoho SMTP over TLS 587. Returns Message-ID.
        Raises SMTPSendError on failure.
        """
        message_id = make_msgid(domain=self.username.split("@")[-1])
        msg = MIMEMultipart("alternative")
        msg["From"] = self.username
        msg["To"] = to_address
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = message_id

        if thread_message_id:
            msg["In-Reply-To"] = thread_message_id
            msg["References"] = thread_message_id

        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(ZOHO_SMTP_HOST, ZOHO_SMTP_PORT, timeout=30.0) as server:
                server.ehlo()
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.username, to_address, msg.as_string())
                logger.info("Email sent to %s, Message-ID: %s", to_address, message_id)
                return message_id
        except smtplib.SMTPException as e:
            logger.error("SMTP send rejected: %s", e)
            raise SMTPSendError(str(e)) from e

class SMTPSendError(Exception):
    pass
```

### 3. Send Attempt Lifecycle Service

```python
import asyncio
import hashlib
from datetime import datetime
from sqlalchemy import text

# Auxiliary in-process concurrency lock to reduce single-process contention.
# Note: SQLite-backed transactions (BEGIN IMMEDIATE) and table UNIQUE constraints
# are the authoritative safeguards across processes and restarts.
delivery_lock = asyncio.Lock()

async def dispatch_approved_email(
    db: Session,
    thread_id: int,
    draft_id: int,
    approval_id: int
) -> SendAttempt:
    async with delivery_lock:
        # SQLite transaction coordination begins authoritatively
        db.execute(text("BEGIN IMMEDIATE"))
        thread = db.get(OutreachThread, thread_id)
        draft = db.get(Draft, draft_id)
        approval = db.get(Approval, approval_id)
        email_addr = db.get(EmailAddress, thread.selected_email_address_id)

        # 1. Enforce 10 pre-send checks
        pre_send_checks(db, thread_id, draft_id, approval_id)

        # 2. Verify SHA-256 approval content hash
        expected_hash = hashlib.sha256(
            f"{email_addr.address.strip().lower()}\n{draft.subject.strip()}\n{draft.body.strip()}\n{draft.id}\n{draft.version}".encode()
        ).hexdigest()
        if expected_hash != approval.approved_content_hash:
            raise PreSendCheckError("Content integrity violation: Draft altered after approval.")

        # 3. Create persistent SendAttempt in 'pending' state
        idempotency_key = hashlib.sha256(f"{thread_id}_{draft_id}_{approval_id}".encode()).hexdigest()
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
        db.commit()  # Persist BEFORE network socket opened

        # 4. Transition to 'sending'
        attempt.status = "sending"
        attempt.started_at = datetime.utcnow()
        db.commit()

        # 5. Execute Dispatch (Dry-Run vs Live)
        if get_settings().dry_run:
            attempt.status = "sent"
            attempt.completed_at = datetime.utcnow()
            attempt.message_id = f"<dry-run-{idempotency_key[:12]}@local>"
            create_outreach_event(db, attempt)
            db.commit()
            return attempt

        # Live SMTP delivery
        try:
            thread_msg_id = get_thread_message_id(db, thread_id) if draft.draft_type == "followup" else None
            client = ZohoSMTPClient()
            message_id = client.send(
                to_address=email_addr.address,
                subject=draft.subject,
                body=draft.body,
                thread_message_id=thread_msg_id
            )
            attempt.status = "sent"
            attempt.message_id = message_id
            attempt.completed_at = datetime.utcnow()
            create_outreach_event(db, attempt)
            schedule_followups(db, thread_id)
            db.commit()
            return attempt
        except SMTPSendError as e:
            attempt.status = "failed"
            attempt.error_message = str(e)
            attempt.completed_at = datetime.utcnow()
            db.commit()
            raise
        except Exception as e:
            # Indeterminate failure: connection dropped or timed out
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

    # 1. Exact version approval
    approval = db.get(Approval, approval_id)
    if not approval or approval.draft_id != draft_id:
        raise PreSendCheckError("No valid approval record for this exact draft version")

    # 2. Global pause
    if config.get("sending_paused") == "true":
        raise PreSendCheckError("Global sending pause is active")

    # 3. Daily quota (counted from outreach_events table)
    today_sent = count_sent_today(db)
    limit = int(config.get("daily_sending_limit", "20"))
    if today_sent >= limit:
        raise PreSendCheckError(f"Daily sending limit of {limit} reached ({today_sent} sent today)")

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
        raise PreSendCheckError(f"Selected email address not eligible: {reason}")

    # 8. Catch-all separate explicit approval
    verification = get_latest_verification(db, email_addr.id)
    if verification and verification.status == "catch-all" and not verification.catch_all_approved:
        raise PreSendCheckError("Catch-all address requires separate explicit manual approval")

    # 9. Duplicate send prevention
    existing = db.scalar(
        select(OutreachEvent).where(
            OutreachEvent.outreach_thread_id == thread_id,
            OutreachEvent.event_type == draft.draft_type,
            OutreachEvent.followup_number == draft.followup_number
        )
    )
    if existing:
        raise PreSendCheckError("An outreach message has already been sent for this thread and event type")

    # 10. Outreach thread eligibility
    if thread.status in ("suppressed", "replied", "bounced", "closed"):
        raise PreSendCheckError(f"Outreach thread not eligible for sending (status: {thread.status})")
```

### 5. Daily Quota Management
Always count from `outreach_events` in SQLite:
```python
def count_sent_today(db: Session) -> int:
    today_start = datetime.combine(date.today(), datetime.min.time())
    return db.scalar(
        select(func.count(OutreachEvent.id))
        .where(OutreachEvent.sent_at >= today_start)
    ) or 0
```

### 6. Zoho IMAP Inbound Monitoring

```python
# app/integrations/zoho_imap.py
import imaplib
import email
import logging

ZOHO_IMAP_HOST = "imap.zoho.com"
ZOHO_IMAP_PORT = 993

class ZohoIMAPClient:
    def __init__(self):
        settings = get_settings()
        self.username = settings.zoho_imap_username
        self.password = settings.zoho_imap_password
        if not self.username or not self.password:
            raise ValueError("Zoho IMAP credentials not configured in environment.")

    def fetch_unread_messages(self) -> list[dict]:
        messages = []
        with imaplib.IMAP4_SSL(ZOHO_IMAP_HOST, ZOHO_IMAP_PORT) as mail:
            mail.login(self.username, self.password)
            mail.select("INBOX")
            _, message_ids = mail.search(None, "UNSEEN")
            for msg_id in message_ids[0].split():
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                parsed = email.message_from_bytes(msg_data[0][1])
                messages.append({
                    "message_id": parsed.get("Message-ID", "").strip(),
                    "in_reply_to": parsed.get("In-Reply-To", "").strip(),
                    "from": parsed.get("From", ""),
                    "subject": parsed.get("Subject", ""),
                    "date": parsed.get("Date", ""),
                    "is_dsn": "delivery-status" in parsed.get_content_type(),
                    "bounced_address": self._extract_bounced_address(parsed)
                })
        return messages
```

---

## Testing Requirements

- Mock `smtplib.SMTP` and `imaplib.IMAP4_SSL` in all tests.
- Test that send-attempt is committed to database in `pending` state before SMTP transmission.
- Test that SMTP connection failure transitions attempt to `failed` or `unknown`.
- Test that attempts in `unknown` state are never automatically retried.
- Test that SQLite transactional coordination and unique idempotency keys block duplicate send attempts at the database level across concurrent workers.
- Test that auxiliary in-process delivery lock serializes concurrent threads.
- Test dry-run mode executes state transitions and generates simulated message IDs.
