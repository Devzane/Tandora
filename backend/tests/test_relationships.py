"""Integration tests verifying domain model relationships:
1. One company has multiple opportunities and contacts.
2. One opportunity has multiple contacts.
3. A contact can be linked to multiple opportunities without duplicating the contact record.
4. Cascading behavior on deletion and unlinking.
5. Foreign-key and integrity constraints on junction tables.
"""

import pytest
from fastapi.testclient import TestClient


def test_one_company_multiple_opportunities_and_contacts(client: TestClient):
    """Verify that a single company can have multiple opportunities and contacts."""
    # 1. Create company
    c_resp = client.post("/api/v1/companies/", json={"name": "Acme Corp", "type": "employer"})
    assert c_resp.status_code == 201
    company_id = c_resp.json()["id"]

    # 2. Create 2 opportunities for this company
    opp1 = client.post(
        "/api/v1/opportunities/",
        json={"company_id": company_id, "title": "Senior DevOps Engineer", "type": "employment"},
    ).json()
    opp2 = client.post(
        "/api/v1/opportunities/",
        json={"company_id": company_id, "title": "Staff Platform Engineer", "type": "employment"},
    ).json()

    # 3. Create 2 contacts employed at this company
    ct1 = client.post(
        "/api/v1/contacts/",
        json={"first_name": "Alice", "last_name": "Smith", "company_id": company_id},
    ).json()
    ct2 = client.post(
        "/api/v1/contacts/",
        json={"first_name": "Bob", "last_name": "Jones", "company_id": company_id},
    ).json()

    # 4. Verify company's opportunities via API
    opps_resp = client.get(f"/api/v1/companies/{company_id}/opportunities")
    assert opps_resp.status_code == 200
    opps = opps_resp.json()
    assert len(opps) == 2
    opp_titles = {o["title"] for o in opps}
    assert "Senior DevOps Engineer" in opp_titles
    assert "Staff Platform Engineer" in opp_titles

    # 5. Verify company's contacts via API
    cts_resp = client.get(f"/api/v1/companies/{company_id}/contacts")
    assert cts_resp.status_code == 200
    cts = cts_resp.json()
    assert len(cts) == 2
    ct_names = {c["full_name"] for c in cts}
    assert "Alice Smith" in ct_names
    assert "Bob Jones" in ct_names


def test_one_opportunity_multiple_contacts(client: TestClient):
    """Verify that a single opportunity can link multiple contacts (e.g. recruiter and hiring manager)."""
    # 1. Create company and opportunity
    c_resp = client.post("/api/v1/companies/", json={"name": "Tech Corp", "type": "employer"}).json()
    opp_resp = client.post(
        "/api/v1/opportunities/",
        json={"company_id": c_resp["id"], "title": "Cloud Architect", "type": "employment"},
    ).json()
    opp_id = opp_resp["id"]

    # 2. Create two contacts (Recruiter and Engineering Director)
    recruiter = client.post(
        "/api/v1/contacts/",
        json={"first_name": "Rachel", "last_name": "Recruiter", "company_id": c_resp["id"]},
    ).json()
    director = client.post(
        "/api/v1/contacts/",
        json={"first_name": "David", "last_name": "Director", "company_id": c_resp["id"]},
    ).json()

    # 3. Link both contacts to the opportunity
    l1 = client.post(f"/api/v1/opportunities/{opp_id}/contacts/{recruiter['id']}")
    assert l1.status_code == 201
    l2 = client.post(f"/api/v1/opportunities/{opp_id}/contacts/{director['id']}")
    assert l2.status_code == 201

    # 4. Query contacts linked to the opportunity
    opp_cts_resp = client.get(f"/api/v1/opportunities/{opp_id}/contacts")
    assert opp_cts_resp.status_code == 200
    linked_cts = opp_cts_resp.json()
    assert len(linked_cts) == 2
    linked_ids = {c["id"] for c in linked_cts}
    assert recruiter["id"] in linked_ids
    assert director["id"] in linked_ids


def test_contact_linked_to_multiple_opportunities_without_duplication(client: TestClient):
    """Verify that a single contact can be linked to multiple opportunities
    (e.g., external recruiter representing multiple clients, or executive across projects)
    WITHOUT duplicating the contact record.
    """
    # 1. Create two separate client companies
    comp_a = client.post("/api/v1/companies/", json={"name": "Client A", "type": "employer"}).json()
    comp_b = client.post("/api/v1/companies/", json={"name": "Client B", "type": "freelance_client"}).json()

    # 2. Create an opportunity under each company
    opp_a = client.post(
        "/api/v1/opportunities/",
        json={"company_id": comp_a["id"], "title": "Lead SRE", "type": "employment"},
    ).json()
    opp_b = client.post(
        "/api/v1/opportunities/",
        json={"company_id": comp_b["id"], "title": "Infrastructure Audit", "type": "freelance_prospect"},
    ).json()

    # 3. Create a single contact (e.g. independent recruiter or agency partner)
    contact = client.post(
        "/api/v1/contacts/",
        json={"first_name": "Sarah", "last_name": "Agency", "headline": "Technical Talent Partner"},
    ).json()
    contact_id = contact["id"]
    contact_external_id = contact["external_id"]

    # 4. Link the SAME contact to both opportunities
    link_a = client.post(f"/api/v1/opportunities/{opp_a['id']}/contacts/{contact_id}")
    assert link_a.status_code == 201

    link_b = client.post(f"/api/v1/opportunities/{opp_b['id']}/contacts/{contact_id}")
    assert link_b.status_code == 201

    # 5. Query opportunities for this contact
    c_opps_resp = client.get(f"/api/v1/contacts/{contact_id}/opportunities")
    assert c_opps_resp.status_code == 200
    c_opps = c_opps_resp.json()
    assert len(c_opps) == 2
    linked_opp_ids = {o["id"] for o in c_opps}
    assert opp_a["id"] in linked_opp_ids
    assert opp_b["id"] in linked_opp_ids

    # 6. Verify that the contact was NOT duplicated: exactly one contact exists
    all_contacts = client.get("/api/v1/contacts/").json()
    matching_contacts = [c for c in all_contacts["items"] if c["first_name"] == "Sarah" and c["last_name"] == "Agency"]
    assert len(matching_contacts) == 1
    assert matching_contacts[0]["id"] == contact_id
    assert matching_contacts[0]["external_id"] == contact_external_id


def test_unlink_contact_leaves_both_records_intact(client: TestClient):
    """Verify that unlinking a contact from an opportunity removes only the junction entry."""
    comp = client.post("/api/v1/companies/", json={"name": "Delta Inc"}).json()
    opp = client.post("/api/v1/opportunities/", json={"company_id": comp["id"], "title": "DevOps Consultant"}).json()
    ct = client.post("/api/v1/contacts/", json={"first_name": "Dan", "last_name": "Consultant"}).json()

    # Link
    client.post(f"/api/v1/opportunities/{opp['id']}/contacts/{ct['id']}")
    assert len(client.get(f"/api/v1/opportunities/{opp['id']}/contacts").json()) == 1

    # Unlink
    del_resp = client.delete(f"/api/v1/opportunities/{opp['id']}/contacts/{ct['id']}")
    assert del_resp.status_code == 204

    # Verify link removed
    assert len(client.get(f"/api/v1/opportunities/{opp['id']}/contacts").json()) == 0

    # Verify both records still exist intact
    assert client.get(f"/api/v1/opportunities/{opp['id']}").status_code == 200
    assert client.get(f"/api/v1/contacts/{ct['id']}").status_code == 200


def test_relationship_invalid_foreign_keys_handled(client: TestClient):
    """Verify linking with non-existent opportunity or contact returns 404."""
    # Non-existent opportunity
    r1 = client.post("/api/v1/opportunities/99999/contacts/1")
    assert r1.status_code == 404

    # Create real opp
    comp = client.post("/api/v1/companies/", json={"name": "Zeta LLC"}).json()
    opp = client.post("/api/v1/opportunities/", json={"company_id": comp["id"], "title": "Test Opp"}).json()

    # Non-existent contact
    r2 = client.post(f"/api/v1/opportunities/{opp['id']}/contacts/99999")
    assert r2.status_code == 404
