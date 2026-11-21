---
name: email-verification
description: Reoon Email Verifier API integration — verification caching, result classification, catch-all handling, error handling, and credit tracking for Tandora.
risk: low
source: project
date_added: '2026-11-21'
---

# Email Verification Skill — Tandora

## Purpose

This skill covers the integration with the Reoon Email Verifier API: making verification requests, storing results, enforcing the catch-all approval gate, caching results to conserve credits, and tracking API credit consumption.

## When to Use

Read this skill before implementing `integrations/reoon.py` or `services/verification_service.py`.

## Required Engineering Practices

### Reoon API Client

```python
# app/integrations/reoon.py
import httpx
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

REOON_API_URL = "https://emailverifier.reoon.com/api/v1/verify"

class ReoonClient:
    def __init__(self):
        self.api_key = get_settings().reoon_api_key

    def verify(self, email_address: str) -> dict:
        """
        Verify a single email address via Reoon API.
        Returns the full Reoon JSON response.
        Raises ReoonAPIError on failure.
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    REOON_API_URL,
                    params={"email": email_address, "key": self.api_key, "mode": "power"}
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Reoon API HTTP error: %s", e)
            raise ReoonAPIError(f"Reoon API returned {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error("Reoon API connection error: %s", e)
            raise ReoonAPIError("Could not connect to Reoon API") from e

class ReoonAPIError(Exception):
    pass
```

### Result Classification

Map Reoon API response to the internal status values:

| Reoon Status | Internal Status | Outreach Allowed |
|-------------|-----------------|------------------|
| `safe` | `safe` | Yes |
| `catch_all` | `catch-all` | Only with explicit approval |
| `invalid` | `invalid` | Never |
| `unknown` | `unknown` | Never |
| `risky` | `unknown` | Never |
| `spamtrap` | `invalid` | Never |

```python
REOON_STATUS_MAP = {
    "safe": "safe",
    "catch_all": "catch-all",
    "invalid": "invalid",
    "unknown": "unknown",
    "risky": "unknown",
    "spamtrap": "invalid",
}

def map_reoon_status(reoon_status: str) -> str:
    return REOON_STATUS_MAP.get(reoon_status, "unknown")
```

### Verification Caching

Before calling Reoon, check for a recent verification result:

```python
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select

CACHE_VALID_DAYS = 30

def get_cached_verification(db: Session, email_address_id: int) -> EmailVerification | None:
    cutoff = datetime.utcnow() - timedelta(days=CACHE_VALID_DAYS)
    return db.scalar(
        select(EmailVerification)
        .where(
            EmailVerification.email_address_id == email_address_id,
            EmailVerification.verified_at >= cutoff
        )
        .order_by(EmailVerification.verified_at.desc())
    )
```

If a valid cached result exists, return it without calling Reoon. Write a log message indicating a cached result was returned.

### Verification Service

```python
def verify_email_address(db: Session, email_address_id: int) -> EmailVerification:
    email = get_email_address(db, email_address_id)
    if not email:
        raise ValueError(f"Email address {email_address_id} not found")

    cached = get_cached_verification(db, email_address_id)
    if cached:
        logger.info("Returning cached verification for %d", email_address_id)
        return cached

    client = ReoonClient()
    response = client.verify(email.address)  # May raise ReoonAPIError

    status = map_reoon_status(response.get("status", "unknown"))
    credits_used = response.get("credits_used", 1)

    verification = EmailVerification(
        email_address_id=email_address_id,
        status=status,
        catch_all_approved=0,
        reoon_response=json.dumps(response),
        credits_used=credits_used,
        verified_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=CACHE_VALID_DAYS)
    )
    db.add(verification)
    
    write_audit_log(db, "email_verified", "email_address", email_address_id,
                   f"Verified {email.address}: {status}", {"status": status, "credits": credits_used})
    return verification
```

### Catch-All Approval

```python
def approve_catch_all(db: Session, email_address_id: int) -> EmailVerification:
    verification = get_latest_verification(db, email_address_id)
    if not verification:
        raise ValueError("No verification result found for this address")
    if verification.status != "catch-all":
        raise ValueError("Address is not a catch-all")
    
    verification.catch_all_approved = 1
    verification.catch_all_approved_at = datetime.utcnow()
    
    write_audit_log(db, "catch_all_approved", "email_address", email_address_id,
                   f"Catch-all address manually approved")
    return verification
```

### Address Usability Check

This function is called by draft generation and sending code:

```python
def is_address_usable(db: Session, email_address_id: int) -> tuple[bool, str]:
    """
    Returns (usable: bool, reason: str).
    """
    verification = get_latest_verification(db, email_address_id)
    if not verification:
        return False, "Address has not been verified"
    if verification.status == "safe":
        return True, "safe"
    if verification.status == "catch-all":
        if verification.catch_all_approved:
            return True, "catch-all (approved)"
        return False, "catch-all address requires explicit approval"
    return False, f"Address status is {verification.status}"
```

## Common Mistakes

- Calling Reoon without checking the cache. → Always check cache first.
- Treating a Reoon API error as a "safe" verification. → If Reoon fails, raise an error.
- Allowing catch-all addresses without checking `catch_all_approved`. → Always check the flag.
- Not storing the full Reoon JSON response. → Store it for audit and debugging.
- Not tracking credits. → Always record `credits_used`.

## Security Considerations

- The Reoon API key must come from the `REOON_API_KEY` environment variable.
- Do not log email addresses at DEBUG level in production.
- Do not expose the full Reoon response in API responses to the client (it may contain internal data). Return only the mapped status.

## Testing Requirements

- Mock `httpx.Client` in all tests. Never call the real Reoon API.
- Test all 6 Reoon status values and their internal mappings.
- Test that a cached result is returned without calling Reoon.
- Test that a Reoon API error raises `ReoonAPIError` and does not store a result.
- Test catch-all approval flow.
- Test `is_address_usable` for all status/approval combinations.

## Project-Specific Constraints

- Reoon is the only email verification provider. Do not add alternatives.
- Cache valid for 30 days. After 30 days, re-verify before outreach.
- The `reoon_api_key` is validated when verification is invoked; missing keys produce clear, actionable errors without blocking unrelated features or startup.
- Credits used are tracked per verification call. The total is available via `sum(email_verifications.credits_used)`.
