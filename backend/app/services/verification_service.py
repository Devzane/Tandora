"""Email Verification Service — Reoon lifecycle, 30-day caching, and approved policy enforcement."""

import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.reoon import ReoonClient
from app.models.email_address import EmailAddress
from app.models.email_verification import EmailVerification
from app.services.audit_service import write_audit_log

logger = logging.getLogger(__name__)

CACHE_VALID_DAYS = 30


class KeyedMutexRegistry:
    """Thread-safe registry of mutex locks keyed by integer or string identifier.

    Maintains reference counts for active/waiting threads. Automatically prunes
    unused locks when all waiting threads release them to prevent unbounded
    memory growth in long-running processes.

    Scope Limitation:
        This lock registry provides process-level mutual exclusion for concurrent
        threads within a single application process. It does not provide distributed
        locking across multiple worker processes or multi-host deployments.
    """

    def __init__(self) -> None:
        self._global_lock = threading.Lock()
        self._locks: dict[int, tuple[threading.Lock, int]] = {}

    @contextmanager
    def lock(self, key: int):
        with self._global_lock:
            if key in self._locks:
                lock, ref_count = self._locks[key]
                self._locks[key] = (lock, ref_count + 1)
            else:
                lock = threading.Lock()
                self._locks[key] = (lock, 1)

        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._global_lock:
                lock, ref_count = self._locks[key]
                if ref_count <= 1:
                    self._locks.pop(key, None)
                else:
                    self._locks[key] = (lock, ref_count - 1)

    def active_lock_count(self) -> int:
        """Return the number of tracked locks in the registry (for diagnostics and testing)."""
        with self._global_lock:
            return len(self._locks)


_email_lock_registry = KeyedMutexRegistry()


def get_email_lock_registry() -> KeyedMutexRegistry:
    """Return the module-level email verification lock registry."""
    return _email_lock_registry

# Canonical Power Mode statuses documented by Reoon API:
# safe, invalid, disabled, disposable, inbox_full, catch_all, role_account, spamtrap, unknown
DOCUMENTED_POWER_MODE_STATUSES = {
    "safe": "safe",
    "catch_all": "catch-all",
    "catch-all": "catch-all",
    "role_account": "role_account",
    "invalid": "invalid",
    "disabled": "disabled",
    "disposable": "disposable",
    "inbox_full": "inbox_full",
    "spamtrap": "spamtrap",
    "unknown": "unknown",
}


def map_reoon_status(reoon_status: str | None) -> tuple[str, bool]:
    """Map raw Reoon Power Mode verification status to canonical internal status.

    Returns:
        tuple[str, bool]: (canonical_status, is_unexpected)
    """
    if not reoon_status:
        logger.warning("Empty Reoon status received; treating safely as 'unknown'")
        return "unknown", True

    normalized = reoon_status.lower().strip()
    if normalized in DOCUMENTED_POWER_MODE_STATUSES:
        return DOCUMENTED_POWER_MODE_STATUSES[normalized], False

    logger.warning(
        "Unexpected Reoon Power Mode status '%s' received. Treating safely as 'unknown' and suppressing.",
        reoon_status,
    )
    return "unknown", True


def get_cached_verification(db: Session, email_address_id: int) -> EmailVerification | None:
    """Return the most recent non-expired verification for an email address, if any."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = (
        select(EmailVerification)
        .where(
            EmailVerification.email_address_id == email_address_id,
            EmailVerification.expires_at > now,
        )
        .order_by(EmailVerification.verified_at.desc())
    )
    return db.execute(stmt).scalars().first()


def get_latest_verification(db: Session, email_address_id: int) -> EmailVerification | None:
    """Return the most recent verification for an email address regardless of expiry."""
    stmt = (
        select(EmailVerification)
        .where(EmailVerification.email_address_id == email_address_id)
        .order_by(EmailVerification.verified_at.desc())
    )
    return db.execute(stmt).scalars().first()


def verify_email_address(
    db: Session,
    email_address_id: int,
    force: bool = False,
    client: ReoonClient | None = None,
) -> tuple[EmailVerification, bool]:
    """Verify an email address via Reoon or return cached verification.

    Thread-safe synchronization:
    Acquires an in-process lock keyed by email_address_id, preventing concurrent
    duplicate requests from triggering redundant Reoon API calls or consuming
    duplicate credits. Uses double-checked locking to return committed cached
    results to waiting requests.

    Approved Policy:
    - safe: Automatically approved.
    - catch_all: Automatically approved.
    - role_account: Automatically approved.
    - invalid: Automatically suppressed.
    - unknown: Automatically suppressed.
    - disposable: Automatically suppressed.
    - spamtrap: Automatically suppressed.
    - disabled: Automatically suppressed.
    - inbox_full: Automatically suppressed pending an explicitly defined recovery policy.

    Technical failures (timeouts, network errors, HTTP 5xx, missing API keys) raise
    exceptions and do NOT insert records or modify suppression flags.

    Returns:
        tuple[EmailVerification, bool]: (verification_record, was_cached)
    """
    with _email_lock_registry.lock(email_address_id):
        # Invalidate local session identity cache so waiting threads see freshly committed transactions
        db.expire_all()

        email_obj = db.get(EmailAddress, email_address_id)
        if not email_obj:
            raise ValueError(f"Email address ID {email_address_id} not found")

        # Double-checked locking: check 30-day cache after acquiring the lock
        if not force:
            cached = get_cached_verification(db, email_address_id)
            if cached:
                logger.info("Returning cached verification for email %d (%s)", email_address_id, email_obj.address)
                return cached, True

        # External HTTP request: executed only after confirming uncached state under lock
        reoon_client = client or ReoonClient()
        response = reoon_client.verify(email_obj.address)

        raw_status = response.get("status")
        status, is_unexpected = map_reoon_status(raw_status)

        # Billing & Credit Accounting:
        # 1. If Reoon explicitly provides 'credits_used', use it.
        # 2. According to Reoon's billing rules: unknown/inconclusive results are refunded/billed 0 credits.
        # 3. Conclusive results consume 1 credit.
        if "credits_used" in response:
            credits_used = int(response["credits_used"])
        else:
            credits_used = 0 if status == "unknown" else 1

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now + timedelta(days=CACHE_VALID_DAYS)

        # Policy: safe, catch_all, and role_account are automatically approved.
        is_catch_all = (status == "catch-all")
        catch_all_approved = 1 if is_catch_all else 0
        catch_all_approved_at = now if is_catch_all else None

        verification = EmailVerification(
            email_address_id=email_address_id,
            status=status,
            catch_all_approved=catch_all_approved,
            catch_all_approved_at=catch_all_approved_at,
            reoon_response=json.dumps(response),
            credits_used=credits_used,
            verified_at=now,
            expires_at=expires_at,
        )
        db.add(verification)

        # Automatic suppression policy on undeliverable/unverified statuses:
        # invalid, unknown, disposable, spamtrap, disabled, inbox_full
        if status in ("invalid", "unknown", "disposable", "spamtrap", "disabled", "inbox_full"):
            email_obj.suppressed = 1
            if status == "inbox_full":
                email_obj.suppressed_reason = "Reoon verification: inbox_full (mailbox full, recovery pending)"
            elif is_unexpected:
                email_obj.suppressed_reason = f"Reoon verification: unexpected status '{raw_status}'"
            else:
                email_obj.suppressed_reason = f"Reoon verification: {status}"
            email_obj.suppressed_at = now
            email_obj.updated_at = now

        db.flush()

        write_audit_log(
            db,
            event_type="email_verified",
            description=f"Verified email '{email_obj.address}': status={status}, credits={credits_used}",
            entity_type="email_address",
            entity_id=email_address_id,
            metadata={
                "status": status,
                "raw_status": raw_status,
                "credits_used": credits_used,
                "is_safe_to_send": response.get("is_safe_to_send"),
                "forced": force,
                "is_unexpected": is_unexpected,
            },
        )

        # Commit before releasing the mutex so concurrent waiters find the committed result in cache
        db.commit()

        return verification, False


def approve_catch_all(db: Session, email_address_id: int) -> EmailVerification:
    """Explicit catch-all approval handler.

    Under the approved policy, catch-all addresses are already automatically approved
    upon verification (catch_all_approved = 1). This function confirms the approval.
    """
    email_obj = db.get(EmailAddress, email_address_id)
    if not email_obj:
        raise ValueError(f"Email address ID {email_address_id} not found")

    verification = get_latest_verification(db, email_address_id)
    if not verification:
        raise ValueError("No verification result found for this email address")
    if verification.status != "catch-all":
        raise ValueError(f"Address status is '{verification.status}', not 'catch-all'")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    verification.catch_all_approved = 1
    if not verification.catch_all_approved_at:
        verification.catch_all_approved_at = now
    db.flush()

    write_audit_log(
        db,
        event_type="catch_all_approved",
        description=f"Confirmed catch-all approval for '{email_obj.address}'",
        entity_type="email_address",
        entity_id=email_address_id,
        metadata={"verification_id": verification.id},
    )

    return verification


def is_address_usable(db: Session, email_address_id: int) -> tuple[bool, str]:
    """Check whether an email address is eligible for outreach drafting and sending.

    Approved Policy:
    - safe: Usable (automatically approved).
    - catch-all: Usable (automatically approved).
    - role_account: Usable (automatically approved).
    - invalid, unknown, disposable, spamtrap, disabled, inbox_full: Unusable (suppressed).
    - Unverified or expired (>30 days): Unusable.

    Returns:
        tuple[bool, str]: (is_usable, reason)
    """
    email_obj = db.get(EmailAddress, email_address_id)
    if not email_obj:
        return False, "Email address not found"
    if email_obj.suppressed:
        return False, f"Address is suppressed: {email_obj.suppressed_reason or 'Suppressed'}"

    verification = get_latest_verification(db, email_address_id)
    if not verification:
        return False, "Address has not been verified"

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if verification.expires_at <= now:
        return False, "Verification has expired (older than 30 days)"

    if verification.status in ("safe", "catch-all", "role_account"):
        return True, verification.status

    if verification.status == "inbox_full":
        return False, "Mailbox is full (inbox_full, recovery pending)"

    return False, f"Address verification status is {verification.status}"


def get_verification_stats(db: Session) -> dict[str, Any]:
    """Return aggregated verification and credit consumption statistics."""
    total_verifications = db.scalar(select(func.count()).select_from(EmailVerification)) or 0
    total_credits = db.scalar(select(func.sum(EmailVerification.credits_used))) or 0

    status_counts_stmt = select(EmailVerification.status, func.count()).group_by(EmailVerification.status)
    status_counts = dict(db.execute(status_counts_stmt).all())

    # Count addresses suppressed by Reoon verification
    suppressed_by_verification = db.scalar(
        select(func.count())
        .select_from(EmailAddress)
        .where(
            EmailAddress.suppressed == 1,
            EmailAddress.suppressed_reason.like("Reoon verification%"),
        )
    ) or 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    approved_count = db.scalar(
        select(func.count())
        .select_from(EmailVerification)
        .join(EmailAddress, EmailVerification.email_address_id == EmailAddress.id)
        .where(
            EmailVerification.status.in_(["safe", "catch-all", "role_account"]),
            EmailVerification.expires_at > now,
            EmailAddress.suppressed == 0,
        )
    ) or 0

    return {
        "total_verifications": total_verifications,
        "total_credits_used": total_credits,
        "status_breakdown": status_counts,
        "unapproved_catchalls": 0,
        "suppressed_by_verification": suppressed_by_verification,
        "approved_active_count": approved_count,
    }
