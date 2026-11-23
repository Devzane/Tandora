"""Tests for REST API CRUD and Ingestion endpoints."""

from app.config import get_settings


def test_api_companies_crud(client):
    """Verify REST API endpoints for companies."""
    # Create
    r = client.post(
        "/api/v1/companies/",
        json={
            "name": "Massive Dynamic",
            "website": "https://massivedynamic.com",
            "industry": "Advanced Tech",
            "type": "employer",
        },
    )
    assert r.status_code == 201
    comp = r.json()
    assert comp["name"] == "Massive Dynamic"
    assert comp["id"] is not None
    comp_id = comp["id"]

    # List
    r = client.get("/api/v1/companies/")
    assert r.status_code == 200
    res = r.json()
    assert res["total"] >= 1
    assert any(c["id"] == comp_id for c in res["items"])

    # Detail
    r = client.get(f"/api/v1/companies/{comp_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Massive Dynamic"

    # Update
    r = client.patch(f"/api/v1/companies/{comp_id}", json={"industry": "Applied Sciences"})
    assert r.status_code == 200
    assert r.json()["industry"] == "Applied Sciences"

    # Suppress
    r = client.post(
        f"/api/v1/companies/{comp_id}/suppress",
        json={"suppressed": True, "reason": "Acquired"},
    )
    assert r.status_code == 200
    assert r.json()["suppressed"] == 1
    assert r.json()["suppressed_reason"] == "Acquired"


def test_api_opportunities_crud(client):
    """Verify REST API endpoints for opportunities."""
    # Create company first
    r_comp = client.post("/api/v1/companies/", json={"name": "Hooli", "type": "employer"})
    comp_id = r_comp.json()["id"]

    # Create opportunity
    r = client.post(
        "/api/v1/opportunities/",
        json={
            "company_id": comp_id,
            "title": "Principal Distributed Systems Engineer",
            "type": "employment",
            "status": "active",
        },
    )
    assert r.status_code == 201
    opp = r.json()
    opp_id = opp["id"]
    assert opp["title"] == "Principal Distributed Systems Engineer"

    # List
    r = client.get(f"/api/v1/opportunities/?company_id={comp_id}")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # Detail
    r = client.get(f"/api/v1/opportunities/{opp_id}")
    assert r.status_code == 200
    assert r.json()["id"] == opp_id

    # Update
    r = client.patch(f"/api/v1/opportunities/{opp_id}", json={"status": "won"})
    assert r.status_code == 200
    assert r.json()["status"] == "won"


def test_api_contacts_crud_and_subresources(client):
    """Verify REST API endpoints for contacts, roles, emails, and phones."""
    # Create contact
    r = client.post(
        "/api/v1/contacts/",
        json={
            "first_name": "Gavin",
            "last_name": "Belson",
            "headline": "Former CEO",
            "linkedin_url": "https://www.linkedin.com/in/gavin-belson",
            "emails": [{"address": "gavin@hooli.xyz", "is_primary": 1, "source": "LinkedIn"}],
        },
    )
    assert r.status_code == 201
    contact = r.json()
    contact_id = contact["id"]
    assert contact["first_name"] == "Gavin"
    assert len(contact["emails"]) == 1

    # Add Role
    r = client.post(
        f"/api/v1/contacts/{contact_id}/roles",
        json={"role": "Chief Executive"},
    )
    assert r.status_code == 201

    # Add second email
    r = client.post(
        f"/api/v1/contacts/{contact_id}/emails",
        json={"address": "gb@tethical.org", "source": "Apollo"},
    )
    assert r.status_code == 201
    email_id = r.json()["id"]

    # Add Phone
    r = client.post(
        f"/api/v1/contacts/{contact_id}/phones",
        json={"number": "+1-555-404-5000", "source": "ContactOut"},
    )
    assert r.status_code == 201

    # Get Contact with all sub-resources
    r = client.get(f"/api/v1/contacts/{contact_id}")
    assert r.status_code == 200
    detail = r.json()
    assert len(detail["roles"]) == 1
    assert len(detail["emails"]) == 2
    assert len(detail["phones"]) == 1

    # Suppress Email
    r = client.post(
        f"/api/v1/contacts/{contact_id}/emails/{email_id}/suppress",
        json={"suppressed": True, "reason": "Inactive domain"},
    )
    assert r.status_code == 200
    assert r.json()["suppressed"] == 1

    # Suppress Contact
    r = client.post(
        f"/api/v1/contacts/{contact_id}/suppress",
        json={"suppressed": True, "reason": "Opt-out"},
    )
    assert r.status_code == 200
    assert r.json()["suppressed"] == 1


def test_api_captures_ingestion(client):
    """Verify POST /api/v1/captures/ ingests full prospect capture payload."""
    payload = {
        "source_type": "extension_manual_paste",
        "source_url": "https://www.linkedin.com/in/richard-hendricks",
        "company": {
            "name": "Pied Piper",
            "website": "https://piedpiper.com",
            "type": "freelance_prospect",
        },
        "opportunity": {
            "title": "Cloud Compression Architecture Review",
            "type": "freelance_prospect",
        },
        "contact": {
            "first_name": "Richard",
            "last_name": "Hendricks",
            "headline": "CEO / Founder",
            "linkedin_url": "https://www.linkedin.com/in/richard-hendricks",
            "emails": [{"address": "richard@piedpiper.com", "is_primary": 1, "source": "ContactOut"}],
            "roles": [{"role": "Founder & CEO"}],
        },
        "raw_payload": {"notes": "Captured via manual copy paste fallback"},
    }

    r = client.post(
        "/api/v1/captures/",
        json=payload,
        headers={"X-Extension-Secret": get_settings().extension_api_secret},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["capture_id"] is not None
    assert data["company_id"] is not None
    assert data["opportunity_id"] is not None
    assert data["contact_id"] is not None
    assert data["duplicate_flag"] == 0
