"""Tests for server-rendered local web UI endpoints."""

from app.schemas.company import CompanyCreate
from app.schemas.opportunity import OpportunityCreate
from app.schemas.contact import ContactCreate, EmailAddressCreate
from app.services.organization_service import create_company, create_opportunity
from app.services.contact_service import create_contact, add_email_address


def test_dashboard_view(client, test_db):
    """Verify GET / renders dashboard with 200 OK and expected content."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Tandora" in response.text
    assert "Dashboard" in response.text
    assert "Total Contacts" in response.text
    assert "Daily Quota Used" in response.text


def test_organizations_views(client, test_db):
    """Verify organization list, new form, create action, detail, and suppression toggle."""
    # List view
    r = client.get("/organizations")
    assert r.status_code == 200
    assert "Organizations" in r.text

    # New form view
    r = client.get("/organizations/new")
    assert r.status_code == 200
    assert "Create New Organization" in r.text

    # Create submission
    r = client.post(
        "/organizations/new",
        data={
            "name": "Wayne Enterprises",
            "type": "employer",
            "industry": "Defense",
            "website": "https://waynecorp.com",
            "description": "Multinational conglomerate",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    redirect_url = r.headers["location"]

    # Detail view
    r = client.get(redirect_url)
    assert r.status_code == 200
    assert "Wayne Enterprises" in r.text
    assert "Defense" in r.text

    company_id = int(redirect_url.split("/")[-1])

    # Suppress action
    r = client.post(
        f"/organizations/{company_id}/suppress",
        data={"suppressed": 1, "reason": "Testing suppression"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Check detail view after suppression
    r = client.get(f"/organizations/{company_id}")
    assert r.status_code == 200
    assert "Organization Suppressed" in r.text


def test_opportunities_views(client, test_db):
    """Verify opportunities list, new form, create action, and detail view."""
    comp = create_company(test_db, CompanyCreate(name="Stark Industries"))
    test_db.commit()

    # List view
    r = client.get("/opportunities")
    assert r.status_code == 200

    # New form view
    r = client.get("/opportunities/new")
    assert r.status_code == 200
    assert "Create New Opportunity" in r.text

    # Create submission
    r = client.post(
        "/opportunities/new",
        data={
            "company_id": comp.id,
            "title": "Lead Robotics Architect",
            "type": "employment",
            "status": "active",
            "description": "Building autonomous systems",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    redirect_url = r.headers["location"]

    # Detail view
    r = client.get(redirect_url)
    assert r.status_code == 200
    assert "Lead Robotics Architect" in r.text
    assert "Stark Industries" in r.text


def test_contacts_views_and_actions(client, test_db):
    """Verify contacts list, new form, create action, detail, sub-actions, and suppression."""
    comp = create_company(test_db, CompanyCreate(name="Cyberdyne Systems"))
    test_db.commit()

    # List view
    r = client.get("/contacts")
    assert r.status_code == 200
    assert "Contacts &amp; Decision-Makers" in r.text or "Contacts" in r.text

    # New form view
    r = client.get("/contacts/new")
    assert r.status_code == 200
    assert "Create New Contact" in r.text

    # Create submission with email and phone
    r = client.post(
        "/contacts/new",
        data={
            "first_name": "Miles",
            "last_name": "Dyson",
            "company_id": comp.id,
            "headline": "Director of Special Projects",
            "linkedin_url": "https://www.linkedin.com/in/miles-dyson",
            "email_address": "miles.dyson@cyberdyne.com",
            "email_source": "ContactOut",
            "phone_number": "+1-555-019-3333",
            "phone_source": "manual",
            "notes": "Key architect",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    contact_url = r.headers["location"]
    contact_id = int(contact_url.split("/")[-1])

    # Detail view
    r = client.get(contact_url)
    assert r.status_code == 200
    assert "Miles" in r.text
    assert "Dyson" in r.text
    assert "miles.dyson@cyberdyne.com" in r.text
    assert "ContactOut" in r.text

    # Add second email address
    r = client.post(
        f"/contacts/{contact_id}/emails",
        data={"address": "m.dyson@personal.net", "source": "Apollo"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Add phone number
    r = client.post(
        f"/contacts/{contact_id}/phones",
        data={"number": "+1-555-999-0000", "type": "work", "source": "Apollo"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Verify both added in detail view
    r = client.get(contact_url)
    assert "m.dyson@personal.net" in r.text
    assert "+1-555-999-0000" in r.text

    # Suppress contact
    r = client.post(
        f"/contacts/{contact_id}/suppress",
        data={"suppressed": 1, "reason": "No longer in role"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.get(contact_url)
    assert "Contact Suppressed" in r.text


def test_suppressions_view(client, test_db):
    """Verify central suppressions view renders suppressed organizations, contacts, and emails."""
    comp = create_company(test_db, CompanyCreate(name="Suppressed Corp"))
    contact, _ = create_contact(test_db, ContactCreate(first_name="Blocked", last_name="User"))
    email = add_email_address(test_db, contact.id, EmailAddressCreate(address="blocked@example.com"))
    test_db.commit()

    # Suppress them
    client.post(f"/organizations/{comp.id}/suppress", data={"suppressed": 1, "reason": "Org DNC"})
    client.post(f"/contacts/{contact.id}/suppress", data={"suppressed": 1, "reason": "Person opt-out"})
    client.post(f"/contacts/{contact.id}/emails/{email.id}/suppress", data={"suppressed": 1, "reason": "Bounced"})

    r = client.get("/suppressions")
    assert r.status_code == 200
    assert "Multi-Level Suppressions" in r.text
    assert "Suppressed Corp" in r.text
    assert "Blocked User" in r.text
    assert "blocked@example.com" in r.text
