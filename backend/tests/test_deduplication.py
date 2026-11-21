"""Tests for deterministic deduplication rules."""

from app.schemas.contact import ContactCreate, EmailAddressCreate
from app.services.deduplication_service import (
    normalize_linkedin_url,
    normalize_email,
)
from app.services.contact_service import create_contact
from app.services.organization_service import create_company
from app.schemas.company import CompanyCreate


def test_normalize_linkedin_url_variations():
    """Verify various LinkedIn profile URLs are normalized to canonical lowercase form without query params."""
    assert normalize_linkedin_url(None) is None
    assert normalize_linkedin_url("") is None
    assert normalize_linkedin_url("   ") is None

    # Query parameters stripped
    url_with_query = "https://www.linkedin.com/in/alex-smith/?utm_source=share&utm_medium=member_desktop"
    assert normalize_linkedin_url(url_with_query) == "https://www.linkedin.com/in/alex-smith"

    # Trailing slashes stripped
    url_trailing_slash = "https://www.linkedin.com/in/alex-smith/"
    assert normalize_linkedin_url(url_trailing_slash) == "https://www.linkedin.com/in/alex-smith"

    # Missing scheme and uppercase letters
    url_no_scheme = "linkedin.com/in/Alex-Smith"
    assert normalize_linkedin_url(url_no_scheme) == "https://www.linkedin.com/in/alex-smith"

    # Regional subdomain
    url_regional = "https://uk.linkedin.com/in/alex-smith"
    assert normalize_linkedin_url(url_regional) == "https://www.linkedin.com/in/alex-smith"


def test_normalize_email_variations():
    """Verify email normalization strips whitespace and converts to lowercase."""
    assert normalize_email(None) is None
    assert normalize_email("  ") is None
    assert normalize_email("  Alex.Smith@Company.COM  ") == "alex.smith@company.com"


def test_deduplication_by_linkedin_url(test_db):
    """Verify contacts with matching normalized LinkedIn URLs are merged into one record."""
    contact1_data = ContactCreate(
        first_name="Alex",
        last_name="Smith",
        headline="Senior DevOps Engineer",
        linkedin_url="https://www.linkedin.com/in/alex-smith/?utm_campaign=profile",
    )
    contact1, merged1 = create_contact(test_db, contact1_data)
    test_db.commit()
    assert merged1 is False
    assert contact1.id is not None

    # Second contact with same LinkedIn slug but different query param
    contact2_data = ContactCreate(
        first_name="Alexander",
        last_name="Smith",
        headline="Lead Cloud Architect",
        linkedin_url="https://uk.linkedin.com/in/alex-smith/",
    )
    contact2, merged2 = create_contact(test_db, contact2_data)
    test_db.commit()

    assert merged2 is True
    assert contact2.id == contact1.id
    assert contact2.duplicate_flag == 0


def test_deduplication_by_email_address(test_db):
    """Verify contacts with matching email addresses are merged into the existing contact."""
    contact1_data = ContactCreate(
        first_name="Jane",
        last_name="Doe",
        emails=[EmailAddressCreate(address="jane.doe@example.com", is_primary=1, source="LinkedIn")],
    )
    contact1, merged1 = create_contact(test_db, contact1_data)
    test_db.commit()
    assert merged1 is False

    # Second contact without LinkedIn URL but matching email (different case/whitespace)
    contact2_data = ContactCreate(
        first_name="Janet",
        last_name="Doe",
        emails=[EmailAddressCreate(address="  JANE.DOE@example.com  ", source="ContactOut")],
    )
    contact2, merged2 = create_contact(test_db, contact2_data)
    test_db.commit()

    assert merged2 is True
    assert contact2.id == contact1.id
    assert contact2.duplicate_flag == 0


def test_deduplication_tertiary_signal_flagged_for_review(test_db):
    """Verify First + Last + Company match without matching unique identifier is flagged for manual review."""
    company = create_company(test_db, CompanyCreate(name="Acme Corp"))
    test_db.commit()

    # Original contact
    contact1_data = ContactCreate(
        company_id=company.id,
        first_name="Robert",
        last_name="Johnson",
        headline="Director of IT",
        linkedin_url="https://www.linkedin.com/in/robert-johnson-1",
    )
    contact1, _ = create_contact(test_db, contact1_data)
    test_db.commit()

    # Same name and same company, but different LinkedIn URL
    contact2_data = ContactCreate(
        company_id=company.id,
        first_name="Robert",
        last_name="Johnson",
        headline="IT Director",
        linkedin_url="https://www.linkedin.com/in/robert-johnson-2",
    )
    contact2, merged2 = create_contact(test_db, contact2_data)
    test_db.commit()

    # Must NOT auto-merge
    assert merged2 is False
    assert contact2.id != contact1.id
    # Must flag for user review
    assert contact2.duplicate_flag == 1
    assert contact2.duplicate_of_contact_id == contact1.id


def test_non_matching_contacts_not_flagged(test_db):
    """Verify contacts with different names or different companies are not flagged as duplicates."""
    company1 = create_company(test_db, CompanyCreate(name="Company One"))
    company2 = create_company(test_db, CompanyCreate(name="Company Two"))
    test_db.commit()

    contact1, _ = create_contact(
        test_db,
        ContactCreate(company_id=company1.id, first_name="Sarah", last_name="Connor"),
    )
    test_db.commit()

    # Same name, different company
    contact2, _ = create_contact(
        test_db,
        ContactCreate(company_id=company2.id, first_name="Sarah", last_name="Connor"),
    )
    test_db.commit()
    assert contact2.duplicate_flag == 0
    assert contact2.duplicate_of_contact_id is None
