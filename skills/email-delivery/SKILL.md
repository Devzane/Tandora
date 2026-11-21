---
name: email-delivery
description: Zoho SMTP and IMAP integration for Tandora — sending approved emails, threading, bounce handling, reply detection, sending queues, and rate limits.
risk: low
source: project
date_added: '2026-11-21'
---

# Email Delivery Skill — Tandora

## Purpose

This skill covers outbound email delivery via Zoho SMTP and inbound monitoring via Zoho IMAP: authentication, message threading, bounce detection, reply matching, quota enforcement, and the global pause mechanism.

## When to Use

Read this skill before implementing `integrations/zoho_smtp.py`, `integrations/zoho_imap.py`, `services/sending_service.py`, or `services/inbox_service.py`.

## Required Engineering Practices

### Zoho SMTP Client

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

    def send(self, to_address: str, subject: str, body: str,
             thread_message_id: str | None = None) -> str:
        """
        Send an email via Zoho SMTP. Returns the Message-ID of the sent message.
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
            logger.error("SMTP send failed: %s", e)
            raise SMTPSendError(str(e)) from e

class SMTPSendError(Exception):
    pass
```

### Pre-Send Checklist (10 Mandatory Checks)

This check must run before every outbound send (initial and follow-up) against persistent database records:

```python
def pre_send_checks(db: Session, thread_id: int, draft_id: int, approval_id: int) -> None:
    """
    Raises PreSendCheckError with a descriptive reason if any of the 10 checks fail.
    """
    config = get_app_config(db)
    thread = db.get(OutreachThread, thread_id)
    draft = db.get(Draft, draft_id)
    contact = db.get(Contact, thread.contact_id)
    
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

    # 5. Address suppression (hard bounce check)
    has_hard_bounce = db.scalar(
        select(Bounce).where(
            Bounce.email_address_id == thread.selected_email_address_id,
            Bounce.bounce_type == "hard"
        )
    )
    if has_hard_bounce:
        raise PreSendCheckError("Selected email address has a recorded hard bounce")

    # 6. Verification eligibility
    usable, reason = is_address_usable(db, thread.selected_email_address_id)
    if not usable:
        raise PreSendCheckError(f"Selected email address not eligible: {reason}")

    # 7. Catch-all separate explicit approval
    verification = get_latest_verification(db, thread.selected_email_address_id)
    if verification and verification.status == "catch-all" and not verification.catch_all_approved:
        raise PreSendCheckError("Catch-all address requires separate explicit manual approval")

    # 8. Duplicate send prevention
    existing = db.scalar(
        select(OutreachEvent).where(
            OutreachEvent.outreach_thread_id == thread_id,
            OutreachEvent.event_type == draft.draft_type,
            OutreachEvent.followup_number == draft.followup_number
        )
    )
    if existing:
        raise PreSendCheckError("An outreach message has already been processed for this thread and event type")

    # 9. Outreach thread eligibility
    if thread.status in ("suppressed", "replied", "bounced", "closed"):
        raise PreSendCheckError(f"Outreach thread is not eligible for sending (status: {thread.status})")

    # 10. Content integrity since approval
    if draft.is_edited and draft.created_at > approval.approved_at:
        raise PreSendCheckError("Draft content was modified after approval was granted; re-approval required")

class PreSendCheckError(Exception):
    pass
```

### Daily Quota Management

Always count sent emails from the database, not an in-memory counter:

```python
from datetime import date, datetime
from sqlalchemy import func, select

def count_sent_today(db: Session) -> int:
    today_start = datetime.combine(date.today(), datetime.min.time())
    return db.scalar(
        select(func.count(OutreachEvent.id))
        .where(OutreachEvent.sent_at >= today_start)
    ) or 0
```

### Zoho IMAP Client

```python
# app/integrations/zoho_imap.py
import imaplib
import email
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

ZOHO_IMAP_HOST = "imap.zoho.com"
ZOHO_IMAP_PORT = 993  # SSL

class ZohoIMAPClient:
    def __init__(self):
        settings = get_settings()
        self.username = settings.zoho_imap_username
        self.password = settings.zoho_imap_password

    def fetch_unread_messages(self) -> list[dict]:
        messages = []
        try:
            with imaplib.IMAP4_SSL(ZOHO_IMAP_HOST, ZOHO_IMAP_PORT) as mail:
                mail.login(self.username, self.password)
                mail.select("INBOX")
                _, message_ids = mail.search(None, "UNSEEN")
                for msg_id in message_ids[0].split():
                    _, msg_data = mail.fetch(msg_id, "(RFC822)")
                    raw = msg_data[0][1]
                    parsed = email.message_from_bytes(raw)
                    messages.append({
                        "imap_id": msg_id,
                        "message_id": parsed.get("Message-ID", "").strip(),
                        "in_reply_to": parsed.get("In-Reply-To", "").strip(),
                        "from": parsed.get("From", ""),
                        "subject": parsed.get("Subject", ""),
                        "date": parsed.get("Date", ""),
                        "is_dsn": self._is_dsn(parsed),
                        "bounced_address": self._extract_bounced_address(parsed),
                        "snippet": self._get_snippet(parsed),
                    })
        except imaplib.IMAP4.error as e:
            logger.error("IMAP error: %s", e)
            raise IMAPError(str(e)) from e
        return messages

    def _is_dsn(self, msg) -> bool:
        content_type = msg.get_content_type()
        return "delivery-status" in content_type or "report" in content_type

    def _extract_bounced_address(self, msg) -> str | None:
        for part in msg.walk():
            if part.get_content_type() == "message/delivery-status":
                payload = part.get_payload(decode=True)
                if payload:
                    for line in payload.decode().split("\n"):
                        if line.startswith("Final-Recipient:"):
                            return line.split("rfc822;")[-1].strip()
        return None

    def _get_snippet(self, msg) -> str:
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True)
                if body:
                    return body.decode("utf-8", errors="replace")[:500]
        return ""

class IMAPError(Exception):
    pass
```

## Common Mistakes

- Forgetting `In-Reply-To` and `References` headers on follow-up emails. → Breaks email client conversation threading.
- Using in-memory counters for rate limits. → Disappears on server restart. Always query `outreach_events`.
- Bypassing pre-send checks in follow-up scheduling routines. → All sends must pass `pre_send_checks`.
- Re-verifying or changing email address mid-thread. → Thread must stick to `selected_email_address_id`.

## Security Considerations

- Use app passwords for Zoho SMTP and IMAP rather than account passwords.
- Always enforce TLS/SSL (port 587 STARTTLS for SMTP, port 993 SSL for IMAP).
- The global pause toggle is an absolute circuit-breaker: check it first before any outbound communication.

## Testing Requirements

- Mock `smtplib.SMTP` and `imaplib.IMAP4_SSL` in all tests.
- Test all 7 pre-send checks individually with negative assertions.
- Test that reaching 20 emails blocks the 21st attempt.
- Test that global pause aborts sending immediately.
- Test that IMAP reply detection suppresses pending follow-ups for that thread.

## Project-Specific Constraints

- Daily sending quota: exactly 20 emails globally (initial outreach + follow-ups combined).
- Zoho SMTP and IMAP endpoints only.
- Strict one recipient address per outreach thread.
