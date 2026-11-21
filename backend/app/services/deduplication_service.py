"""Deduplication Service for Contacts and Accounts."""

import re
from urllib.parse import urlparse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.contact import Contact
from app.models.email_address import EmailAddress


def normalize_linkedin_url(url: str | None) -> str | None:
    """Normalize a LinkedIn profile URL to canonical https://www.linkedin.com/in/<slug> form."""
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    # Prepend scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        # Extract slug after /in/
        match = re.search(r"/in/([^/?#]+)", path, re.IGNORECASE)
        if match:
            slug = match.group(1).lower().strip()
            return f"https://www.linkedin.com/in/{slug}"
        # Fallback if already path-only or different format
        cleaned_path = path.lower()
        if cleaned_path.startswith("/in/"):
            return f"https://www.linkedin.com{cleaned_path}"
        return f"https://www.linkedin.com{cleaned_path}"
    except Exception:
        return url.lower().split("?")[0].rstrip("/")


def normalize_email(email: str | None) -> str | None:
    """Normalize email address: trim whitespace and lowercase."""
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned if cleaned else None


def find_existing_contact(
    db: Session,
    normalized_linkedin: str | None,
    email: str | None,
    first_name: str,
    last_name: str | None,
    company_id: int | None,
) -> tuple[Contact | None, bool, Contact | None]:
    """Determine whether a prospect matches an existing contact or flags a candidate duplicate.

    Returns:
        (existing_contact, is_candidate_duplicate, candidate_match)
        - If exact LinkedIn match: (existing_contact, False, None)
        - If exact Email match: (existing_contact, False, None)
        - If name + company match without exact LinkedIn/Email: (None, True, candidate_match)
        - Otherwise: (None, False, None)
    """
    # 1. Primary Signal: Normalized LinkedIn Profile URL
    if normalized_linkedin:
        stmt = select(Contact).where(Contact.normalized_linkedin_url == normalized_linkedin)
        contact = db.execute(stmt).scalars().first()
        if contact:
            return contact, False, None

    # 2. Secondary Signal: Normalized Email Address
    normalized_addr = normalize_email(email)
    if normalized_addr:
        stmt = (
            select(Contact)
            .join(EmailAddress, EmailAddress.contact_id == Contact.id)
            .where(EmailAddress.address == normalized_addr)
        )
        contact = db.execute(stmt).scalars().first()
        if contact:
            return contact, False, None

    # 3. Tertiary Signal: First Name + Last Name + Company (Candidate Duplicate Flag)
    if first_name and company_id:
        clean_first = first_name.strip().lower()
        query = select(Contact).where(
            Contact.company_id == company_id,
            Contact.first_name.ilike(clean_first),
        )
        if last_name and last_name.strip():
            clean_last = last_name.strip().lower()
            query = query.where(Contact.last_name.ilike(clean_last))

        candidate = db.execute(query).scalars().first()
        if candidate:
            return None, True, candidate

    return None, False, None
