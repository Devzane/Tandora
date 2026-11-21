"""Tests for independent channel provenance tracking."""

from app.schemas.contact import (
    ContactCreate,
    EmailAddressCreate,
    PhoneNumberCreate,
    ContactRoleCreate,
)
from app.services.contact_service import (
    create_contact,
    add_email_address,
    add_phone_number,
    add_contact_role,
    get_contact,
)


def test_independent_email_provenance(test_db):
    """Verify email addresses retain individual source, source_url, and captured_at."""
    contact, _ = create_contact(test_db, ContactCreate(first_name="Marcus", last_name="Vance"))
    test_db.commit()

    # Add work email from ContactOut
    email1 = add_email_address(
        test_db,
        contact.id,
        EmailAddressCreate(
            address="marcus.vance@work.com",
            is_primary=1,
            source="ContactOut",
            source_url="https://contactout.com/marcus-vance",
        ),
    )
    # Add personal email from Apollo
    email2 = add_email_address(
        test_db,
        contact.id,
        EmailAddressCreate(
            address="m.vance@gmail.com",
            is_primary=0,
            source="Apollo",
            source_url="https://app.apollo.io/#/people/123",
        ),
    )
    test_db.commit()

    refreshed = get_contact(test_db, contact.id)
    assert len(refreshed.emails) == 2

    e1 = next(e for e in refreshed.emails if e.address == "marcus.vance@work.com")
    assert e1.source == "ContactOut"
    assert e1.source_url == "https://contactout.com/marcus-vance"
    assert e1.captured_at is not None
    assert e1.is_primary == 1

    e2 = next(e for e in refreshed.emails if e.address == "m.vance@gmail.com")
    assert e2.source == "Apollo"
    assert e2.source_url == "https://app.apollo.io/#/people/123"
    assert e2.is_primary == 0


def test_phone_number_provenance(test_db):
    """Verify phone numbers retain source and type."""
    contact, _ = create_contact(test_db, ContactCreate(first_name="Diana", last_name="Prince"))
    test_db.commit()

    phone1 = add_phone_number(
        test_db,
        contact.id,
        PhoneNumberCreate(
            number="+1-555-010-9999",
            type="mobile",
            is_primary=1,
            source="LinkedIn",
        ),
    )
    phone2 = add_phone_number(
        test_db,
        contact.id,
        PhoneNumberCreate(
            number="+1-555-010-8888",
            type="direct",
            is_primary=0,
            source="Apollo",
        ),
    )
    test_db.commit()

    refreshed = get_contact(test_db, contact.id)
    assert len(refreshed.phones) == 2
    p1 = next(p for p in refreshed.phones if p.number == "+1-555-010-9999")
    assert p1.source == "LinkedIn"
    assert p1.type == "mobile"

    p2 = next(p for p in refreshed.phones if p.number == "+1-555-010-8888")
    assert p2.source == "Apollo"
    assert p2.type == "direct"


def test_contact_roles_attachment(test_db):
    """Verify roles can be attached and tracked."""
    contact, _ = create_contact(test_db, ContactCreate(first_name="Bruce", last_name="Wayne"))
    test_db.commit()

    add_contact_role(
        test_db,
        contact.id,
        ContactRoleCreate(role="Chief Executive Officer"),
    )
    test_db.commit()

    refreshed = get_contact(test_db, contact.id)
    assert len(refreshed.roles) == 1
    assert refreshed.roles[0].role == "Chief Executive Officer"
