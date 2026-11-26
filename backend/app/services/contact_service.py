"""Contact, Channel Provenance, and Suppression Service."""

from datetime import datetime, timezone
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session, selectinload
from app.models.contact import Contact
from app.models.contact_role import ContactRole
from app.models.email_address import EmailAddress
from app.models.phone_number import PhoneNumber
from app.models.outreach_thread import OutreachThread
from app.models.followup_schedule import FollowupSchedule
from app.schemas.contact import (
    ContactCreate,
    ContactUpdate,
    ContactRoleCreate,
    EmailAddressCreate,
    PhoneNumberCreate,
)
from app.services.deduplication_service import (
    normalize_linkedin_url,
    normalize_email,
    find_existing_contact,
)
from app.services.audit_service import write_audit_log


def create_contact(db: Session, data: ContactCreate) -> tuple[Contact, bool]:
    """Create or merge a contact following deterministic deduplication rules.

    Returns:
        (contact, was_merged)
    """
    normalized_linkedin = normalize_linkedin_url(data.linkedin_url)
    primary_email = data.emails[0].address if data.emails else None
    normalized_primary_email = normalize_email(primary_email)

    existing, is_duplicate_candidate, candidate_match = find_existing_contact(
        db,
        normalized_linkedin=normalized_linkedin,
        email=normalized_primary_email,
        first_name=data.first_name,
        last_name=data.last_name,
        company_id=data.company_id,
    )

    if existing:
        # Exact match (LinkedIn or Email): merge / augment details
        if data.headline and not existing.headline:
            existing.headline = data.headline
        if data.notes:
            existing.notes = (existing.notes or "") + "\n" + data.notes if existing.notes else data.notes
        if normalized_linkedin and not existing.normalized_linkedin_url:
            existing.normalized_linkedin_url = normalized_linkedin
            existing.linkedin_url = data.linkedin_url

        # Attach roles
        for r in data.roles:
            add_contact_role(db, existing.id, r)

        # Attach emails
        for e in data.emails:
            add_email_address(db, existing.id, e)

        # Attach phones
        for p in data.phones:
            add_phone_number(db, existing.id, p)

        existing.updated_at = datetime.now(timezone.utc)
        db.flush()
        write_audit_log(
            db,
            event_type="contact_merged",
            description=f"Merged new prospect data into existing contact ID {existing.id} ({existing.first_name} {existing.last_name or ''})",
            entity_type="contact",
            entity_id=existing.id,
        )
        return existing, True

    # Check candidate duplicate flag (name + company match without unique ID match)
    dup_flag = 1 if is_duplicate_candidate else 0
    dup_of_id = candidate_match.id if candidate_match else None

    full_name = f"{data.first_name.strip()} {data.last_name.strip() if data.last_name else ''}".strip()
    contact = Contact(
        company_id=data.company_id,
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip() if data.last_name else None,
        full_name=full_name,
        headline=data.headline.strip() if data.headline else None,
        linkedin_url=data.linkedin_url.strip() if data.linkedin_url else None,
        normalized_linkedin_url=normalized_linkedin,
        notes=data.notes,
        duplicate_flag=dup_flag,
        duplicate_of_contact_id=dup_of_id,
    )
    db.add(contact)
    db.flush()

    for r in data.roles:
        add_contact_role(db, contact.id, r)

    for e in data.emails:
        add_email_address(db, contact.id, e)

    for p in data.phones:
        add_phone_number(db, contact.id, p)

    log_desc = f"Created contact '{contact.first_name} {contact.last_name or ''}'"
    if dup_flag:
        log_desc += f" [FLAGGED POTENTIAL DUPLICATE of Contact ID {dup_of_id}]"

    write_audit_log(
        db,
        event_type="contact_created",
        description=log_desc,
        entity_type="contact",
        entity_id=contact.id,
    )
    return contact, False


def get_contact(db: Session, contact_id: int) -> Contact | None:
    """Fetch contact by ID with all related roles, emails, and phones."""
    stmt = (
        select(Contact)
        .options(
            selectinload(Contact.roles),
            selectinload(Contact.emails).selectinload(EmailAddress.verifications),
            selectinload(Contact.phones),
            selectinload(Contact.company),
        )
        .where(Contact.id == contact_id)
    )
    return db.execute(stmt).scalars().first()


def list_contacts(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    company_id: int | None = None,
    suppressed: int | None = None,
    duplicate_flag: int | None = None,
    search: str | None = None,
) -> tuple[list[Contact], int]:
    """List contacts with filtering and eager loading of relationships."""
    query = (
        select(Contact)
        .options(
            selectinload(Contact.roles),
            selectinload(Contact.emails).selectinload(EmailAddress.verifications),
            selectinload(Contact.phones),
            selectinload(Contact.company),
        )
    )
    if company_id:
        query = query.where(Contact.company_id == company_id)
    if suppressed is not None:
        query = query.where(Contact.suppressed == suppressed)
    if duplicate_flag is not None:
        query = query.where(Contact.duplicate_flag == duplicate_flag)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            (Contact.first_name.ilike(term)) | (Contact.last_name.ilike(term)) | (Contact.headline.ilike(term))
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.execute(query.order_by(Contact.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    return list(items), total


def update_contact(db: Session, contact_id: int, data: ContactUpdate) -> Contact | None:
    """Update contact attributes."""
    contact = get_contact(db, contact_id)
    if not contact:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if field == "linkedin_url":
            contact.linkedin_url = val
            contact.normalized_linkedin_url = normalize_linkedin_url(val)
        else:
            setattr(contact, field, val)

    if "first_name" in update_dict or "last_name" in update_dict:
        contact.full_name = f"{contact.first_name.strip()} {contact.last_name.strip() if contact.last_name else ''}".strip()

    contact.updated_at = datetime.now(timezone.utc)
    db.flush()
    write_audit_log(
        db,
        event_type="contact_updated",
        description=f"Updated contact ID {contact.id} ({contact.first_name} {contact.last_name or ''})",
        entity_type="contact",
        entity_id=contact.id,
    )
    return contact


def set_contact_suppression(
    db: Session, contact_id: int, suppressed: bool, reason: str | None = None
) -> Contact | None:
    """Toggle contact-level suppression and cascade-cancel pending follow-ups for this person."""
    contact = get_contact(db, contact_id)
    if not contact:
        return None

    now = datetime.now(timezone.utc)
    if suppressed:
        contact.suppressed = 1
        contact.suppressed_reason = reason or "Manual suppression"
        contact.suppressed_at = now

        # Multi-level suppression: Cancel pending followups across all outreach threads for this contact
        subquery_threads = select(OutreachThread.id).where(OutreachThread.contact_id == contact_id)
        db.execute(
            update(FollowupSchedule)
            .where(
                FollowupSchedule.outreach_thread_id.in_(subquery_threads),
                FollowupSchedule.status == "pending",
            )
            .values(
                status="cancelled",
                suppressed_reason=f"Contact suppressed: {reason or 'Manual suppression'}",
                suppressed_at=now,
                updated_at=now,
            )
        )
        write_audit_log(
            db,
            event_type="suppression_added",
            description=f"Suppressed contact ID {contact.id} ({contact.first_name} {contact.last_name or ''}): {contact.suppressed_reason}",
            entity_type="contact",
            entity_id=contact.id,
        )
    else:
        contact.suppressed = 0
        contact.suppressed_reason = None
        contact.suppressed_at = None
        write_audit_log(
            db,
            event_type="suppression_removed",
            description=f"Un-suppressed contact ID {contact.id}",
            entity_type="contact",
            entity_id=contact.id,
        )

    contact.updated_at = now
    db.flush()
    return contact


# --- Email & Phone Provenance Operations ---

def add_email_address(db: Session, contact_id: int, data: EmailAddressCreate) -> EmailAddress:
    """Store an email address with explicit provenance tracking."""
    normalized_addr = normalize_email(data.address)
    if not normalized_addr:
        raise ValueError("Invalid email address format")

    # Check if this exact address exists for this contact
    stmt = select(EmailAddress).where(
        EmailAddress.contact_id == contact_id,
        EmailAddress.address == normalized_addr,
    )
    existing = db.execute(stmt).scalars().first()
    if existing:
        return existing

    email_obj = EmailAddress(
        contact_id=contact_id,
        address=normalized_addr,
        is_primary=data.is_primary,
        source=data.source,
        source_url=data.source_url,
        captured_at=datetime.now(timezone.utc),
    )
    db.add(email_obj)
    db.flush()
    write_audit_log(
        db,
        event_type="email_captured",
        description=f"Added email '{email_obj.address}' for contact ID {contact_id} (source={email_obj.source})",
        entity_type="email_address",
        entity_id=email_obj.id,
    )
    return email_obj


def set_email_suppression(
    db: Session, email_id: int, suppressed: bool, reason: str | None = None
) -> EmailAddress | None:
    """Toggle address-level suppression and cancel pending follow-ups for this address."""
    email_obj = db.get(EmailAddress, email_id)
    if not email_obj:
        return None

    now = datetime.now(timezone.utc)
    if suppressed:
        email_obj.suppressed = 1
        email_obj.suppressed_reason = reason or "Manual suppression"
        email_obj.suppressed_at = now

        # Multi-level suppression: Cancel pending followups targeting this address
        subquery_threads = select(OutreachThread.id).where(OutreachThread.selected_email_address_id == email_id)
        db.execute(
            update(FollowupSchedule)
            .where(
                FollowupSchedule.outreach_thread_id.in_(subquery_threads),
                FollowupSchedule.status == "pending",
            )
            .values(
                status="cancelled",
                suppressed_reason=f"Address suppressed: {reason or 'Manual suppression'}",
                suppressed_at=now,
                updated_at=now,
            )
        )
        write_audit_log(
            db,
            event_type="suppression_added",
            description=f"Suppressed email '{email_obj.address}': {email_obj.suppressed_reason}",
            entity_type="email_address",
            entity_id=email_obj.id,
        )
    else:
        email_obj.suppressed = 0
        email_obj.suppressed_reason = None
        email_obj.suppressed_at = None
        write_audit_log(
            db,
            event_type="suppression_removed",
            description=f"Un-suppressed email '{email_obj.address}'",
            entity_type="email_address",
            entity_id=email_obj.id,
        )

    email_obj.updated_at = now
    db.flush()
    return email_obj


def add_phone_number(db: Session, contact_id: int, data: PhoneNumberCreate) -> PhoneNumber:
    """Store a phone number with explicit provenance tracking."""
    stmt = select(PhoneNumber).where(
        PhoneNumber.contact_id == contact_id,
        PhoneNumber.number == data.number.strip(),
    )
    existing = db.execute(stmt).scalars().first()
    if existing:
        return existing

    phone_obj = PhoneNumber(
        contact_id=contact_id,
        number=data.number.strip(),
        type=data.type,
        source=data.source,
        source_url=data.source_url,
        captured_at=datetime.now(timezone.utc),
    )
    db.add(phone_obj)
    db.flush()
    return phone_obj


def add_contact_role(db: Session, contact_id: int, data: ContactRoleCreate) -> ContactRole:
    """Attach a professional role to a contact."""
    stmt = select(ContactRole).where(
        ContactRole.contact_id == contact_id,
        ContactRole.role == data.role.strip(),
    )
    existing = db.execute(stmt).scalars().first()
    if existing:
        return existing

    role_obj = ContactRole(
        contact_id=contact_id,
        role=data.role.strip(),
    )
    db.add(role_obj)
    db.flush()
    return role_obj
