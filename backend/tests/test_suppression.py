"""Tests for multi-level suppression cascades and audit tracking."""

from datetime import date
from sqlalchemy import select
from app.models.outreach_thread import OutreachThread
from app.models.followup_schedule import FollowupSchedule
from app.models.audit_log import AuditLog
from app.schemas.company import CompanyCreate
from app.schemas.opportunity import OpportunityCreate
from app.schemas.contact import ContactCreate, EmailAddressCreate
from app.services.organization_service import (
    create_company,
    create_opportunity,
    set_company_suppression,
)
from app.services.contact_service import (
    create_contact,
    add_email_address,
    set_contact_suppression,
    set_email_suppression,
)


def _setup_thread_with_followup(test_db):
    """Helper fixture to set up company, opportunity, contact, email, thread, and pending followup."""
    company = create_company(test_db, CompanyCreate(name="Initech"))
    opp = create_opportunity(test_db, OpportunityCreate(company_id=company.id, title="Senior Dev"))
    contact, _ = create_contact(test_db, ContactCreate(company_id=company.id, first_name="Peter", last_name="Gibbons"))
    email = add_email_address(test_db, contact.id, EmailAddressCreate(address="peter@initech.com", is_primary=1))
    test_db.flush()

    thread = OutreachThread(
        opportunity_id=opp.id,
        contact_id=contact.id,
        selected_email_address_id=email.id,
        status="sent",
    )
    test_db.add(thread)
    test_db.flush()

    followup = FollowupSchedule(
        outreach_thread_id=thread.id,
        followup_number=1,
        scheduled_date=date(2026, 12, 1),
        status="pending",
    )
    test_db.add(followup)
    test_db.commit()

    return company, opp, contact, email, thread, followup


def test_contact_level_suppression_cancels_followups(test_db):
    """Verify suppressing a contact cascades to cancel pending follow-up schedules."""
    company, opp, contact, email, thread, followup = _setup_thread_with_followup(test_db)

    # Suppress contact
    set_contact_suppression(test_db, contact.id, suppressed=True, reason="Requested unsubscribe")
    test_db.commit()

    test_db.refresh(contact)
    assert contact.suppressed == 1
    assert contact.suppressed_reason == "Requested unsubscribe"
    assert contact.suppressed_at is not None

    test_db.refresh(followup)
    assert followup.status == "cancelled"
    assert "Contact suppressed" in followup.suppressed_reason

    # Verify audit log
    logs = test_db.execute(
        select(AuditLog).where(AuditLog.event_type == "suppression_added", AuditLog.entity_id == contact.id)
    ).scalars().all()
    assert len(logs) == 1

    # Unsuppress contact
    set_contact_suppression(test_db, contact.id, suppressed=False)
    test_db.commit()
    test_db.refresh(contact)
    assert contact.suppressed == 0
    assert contact.suppressed_reason is None


def test_address_level_suppression_cancels_thread_followup(test_db):
    """Verify suppressing an email address cancels pending followups targeting that address."""
    company, opp, contact, email, thread, followup = _setup_thread_with_followup(test_db)

    set_email_suppression(test_db, email.id, suppressed=True, reason="Hard bounce recorded")
    test_db.commit()

    test_db.refresh(email)
    assert email.suppressed == 1
    assert email.suppressed_reason == "Hard bounce recorded"

    test_db.refresh(followup)
    assert followup.status == "cancelled"
    assert "Address suppressed" in followup.suppressed_reason


def test_organization_level_suppression_cancels_all_employed_contacts_followups(test_db):
    """Verify suppressing a company cancels followups across all contacts employed by that company."""
    company, opp, contact, email, thread, followup = _setup_thread_with_followup(test_db)

    set_company_suppression(test_db, company.id, suppressed=True, reason="Company requested DNC")
    test_db.commit()

    test_db.refresh(company)
    assert company.suppressed == 1
    assert company.suppressed_reason == "Company requested DNC"

    test_db.refresh(followup)
    assert followup.status == "cancelled"
    assert "Company suppressed" in followup.suppressed_reason

    # Verify unsuppressing company
    set_company_suppression(test_db, company.id, suppressed=False)
    test_db.commit()
    test_db.refresh(company)
    assert company.suppressed == 0
