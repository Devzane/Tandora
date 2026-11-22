"""Tests for Prospect and Opportunity Capture ingestion, authentication, and deduplication."""

from datetime import datetime, timezone
from app.models.capture import Capture
from app.models.company import Company
from app.models.contact import Contact
from app.models.opportunity import Opportunity
from app.models.opportunity_contact import OpportunityContact
from app.models.linkedin_post import LinkedInPost
from app.models.email_address import EmailAddress
from app.models.phone_number import PhoneNumber
from app.models.audit_log import AuditLog

AUTH_HEADER = {"X-Extension-Secret": "tandora-secure-local-extension-token"}


def test_capture_authentication_missing_secret_returns_401(client):
    """Verify capture endpoint rejects requests missing X-Extension-Secret with HTTP 401."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-noauth",
        "contact": {"first_name": "NoAuth", "last_name": "Tester"},
    }
    response = client.post("/api/v1/captures/", json=payload)
    assert response.status_code == 401
    assert "Invalid or missing extension secret" in response.json()["detail"]


def test_capture_authentication_invalid_secret_returns_401(client):
    """Verify capture endpoint rejects requests with invalid X-Extension-Secret with HTTP 401."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-badauth",
        "contact": {"first_name": "BadAuth", "last_name": "Tester"},
    }
    response = client.post(
        "/api/v1/captures/",
        json=payload,
        headers={"X-Extension-Secret": "incorrect-token-xyz"},
    )
    assert response.status_code == 401
    assert "Invalid or missing extension secret" in response.json()["detail"]


EXPECTED_EXT_ORIGIN = "chrome-extension://hgekmkmaeehbpbegfhgognalocgfhncp"
UNEXPECTED_EXT_ORIGIN = "chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn"


def test_capture_authentication_valid_secret_succeeds(client):
    """Verify capture endpoint accepts requests with valid X-Extension-Secret."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-validauth",
        "contact": {"first_name": "ValidAuth", "last_name": "Tester"},
    }
    response = client.post("/api/v1/captures/", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 201
    data = response.json()
    assert data["capture_id"] is not None
    assert data["contact_id"] is not None


def test_expected_chrome_extension_origin_accepted_with_secret(client):
    """Verify requests originating from the expected Chrome Extension ID are accepted."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-chrome-ext",
        "contact": {"first_name": "ChromeExt", "last_name": "User"},
    }
    headers = {
        "X-Extension-Secret": "tandora-secure-local-extension-token",
        "Origin": EXPECTED_EXT_ORIGIN,
        "Sec-Fetch-Site": "cross-site",
    }
    response = client.post("/api/v1/captures/", json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json()["capture_id"] is not None


def test_unexpected_chrome_extension_origin_rejected_with_403(client):
    """Verify requests from unexpected Chrome extension IDs are rejected with HTTP 403."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-unexpected-ext",
        "contact": {"first_name": "RogueExt", "last_name": "User"},
    }
    headers = {
        "X-Extension-Secret": "tandora-secure-local-extension-token",
        "Origin": UNEXPECTED_EXT_ORIGIN,
    }
    response = client.post("/api/v1/captures/", json=payload, headers=headers)
    assert response.status_code == 403
    assert "Unauthorized extension origin" in response.json()["detail"]


def test_expected_chrome_extension_origin_missing_secret_rejected_with_401(client):
    """Verify request with expected extension ID but missing secret returns HTTP 401."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-expected-ext-nosecret",
        "contact": {"first_name": "NoSecret", "last_name": "User"},
    }
    headers = {
        "Origin": EXPECTED_EXT_ORIGIN,
    }
    response = client.post("/api/v1/captures/", json=payload, headers=headers)
    assert response.status_code == 401
    assert "Invalid or missing extension secret" in response.json()["detail"]


def test_expected_chrome_extension_origin_invalid_secret_rejected_with_401(client):
    """Verify request with expected extension ID but wrong secret returns HTTP 401."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-expected-ext-badsecret",
        "contact": {"first_name": "BadSecret", "last_name": "User"},
    }
    headers = {
        "X-Extension-Secret": "wrong-secret-token-12345",
        "Origin": EXPECTED_EXT_ORIGIN,
    }
    response = client.post("/api/v1/captures/", json=payload, headers=headers)
    assert response.status_code == 401
    assert "Invalid or missing extension secret" in response.json()["detail"]


def test_malicious_web_origin_rejected_by_middleware(client):
    """Verify state-changing POST from malicious web origin is rejected with 403 Forbidden."""
    payload = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/test-malicious",
        "contact": {"first_name": "Evil", "last_name": "Site"},
    }
    headers = {
        "X-Extension-Secret": "tandora-secure-local-extension-token",
        "Origin": "https://evil-cross-origin.com",
    }
    response = client.post("/api/v1/captures/", json=payload, headers=headers)
    assert response.status_code == 403
    assert "Cross-origin request from" in response.json()["detail"]


def test_linkedin_profile_capture_ingestion_with_provenance(client, test_db):
    """Verify complete LinkedIn profile capture ingests entities and preserves channel provenance."""
    capture_time = "2026-11-22T09:30:00Z"
    payload = {
        "capture_type": "linkedin_profile",
        "page_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/sara-chen-tech",
        "source_title": "Sara Chen - VP Engineering - Quantum Labs | LinkedIn",
        "selected_text": "Experienced engineering executive with 15+ years leading teams.",
        "user_notes": "Met at Cloud Expo; actively looking for DevOps leads.",
        "captured_at": capture_time,
        "person": {
            "full_name": "Sara Chen",
            "first_name": "Sara",
            "last_name": "Chen",
            "headline": "VP of Engineering at Quantum Labs",
            "location": "Seattle, WA",
            "linkedin_url": "https://www.linkedin.com/in/sara-chen-tech",
        },
        "contact": {
            "first_name": "Sara",
            "last_name": "Chen",
            "headline": "VP of Engineering at Quantum Labs",
            "location": "Seattle, WA",
            "linkedin_url": "https://www.linkedin.com/in/sara-chen-tech",
            "notes": "Direct capture via extension",
            "roles": [{"role": "VP of Engineering"}],
            "emails": [
                {
                    "address": "sara.chen@quantumlabs.ai",
                    "source": "Apollo",
                    "source_url": "https://www.linkedin.com/in/sara-chen-tech",
                    "is_primary": 1,
                },
                {
                    "address": "schen.personal@gmail.com",
                    "source": "ContactOut",
                    "source_url": "https://www.linkedin.com/in/sara-chen-tech",
                    "is_primary": 0,
                },
            ],
            "phones": [
                {
                    "number": "+1 206-555-0199",
                    "type": "direct",
                    "source": "ContactOut",
                    "source_url": "https://www.linkedin.com/in/sara-chen-tech",
                }
            ],
        },
        "company": {
            "name": "Quantum Labs",
            "website": "https://quantumlabs.ai",
            "industry": "Artificial Intelligence",
            "type": "employer",
        },
        "opportunity": {
            "title": "VP Engineering / Cloud Architecture",
            "type": "employment",
            "source_url": "https://www.linkedin.com/in/sara-chen-tech",
        },
        "raw_payload": {"extension_version": "1.0.0"},
    }

    response = client.post("/api/v1/captures/", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 201
    data = response.json()

    capture_id = data["capture_id"]
    contact_id = data["contact_id"]
    company_id = data["company_id"]
    opportunity_id = data["opportunity_id"]

    assert capture_id is not None
    assert contact_id is not None
    assert company_id is not None
    assert opportunity_id is not None
    assert data["duplicate_flag"] == 0

    # Verify Capture record in DB
    capture = test_db.get(Capture, capture_id)
    assert capture is not None
    assert capture.capture_type == "linkedin_profile"
    assert capture.source_url == "https://www.linkedin.com/in/sara-chen-tech"
    assert capture.contact_id == contact_id
    assert capture.company_id == company_id
    assert capture.opportunity_id == opportunity_id

    # Verify Company in DB
    company = test_db.get(Company, company_id)
    assert company.name == "Quantum Labs"
    assert company.website == "https://quantumlabs.ai"

    # Verify Contact in DB
    contact = test_db.get(Contact, contact_id)
    assert contact.first_name == "Sara"
    assert contact.last_name == "Chen"
    assert contact.normalized_linkedin_url == "https://www.linkedin.com/in/sara-chen-tech"
    assert contact.company_id == company_id

    # Verify Channel Provenance
    emails = test_db.query(EmailAddress).filter(EmailAddress.contact_id == contact_id).all()
    assert len(emails) == 2
    apollo_email = next(e for e in emails if e.address == "sara.chen@quantumlabs.ai")
    assert apollo_email.source == "Apollo"
    assert apollo_email.source_url == "https://www.linkedin.com/in/sara-chen-tech"
    assert apollo_email.is_primary == 1

    contactout_email = next(e for e in emails if e.address == "schen.personal@gmail.com")
    assert contactout_email.source == "ContactOut"
    assert contactout_email.is_primary == 0

    phones = test_db.query(PhoneNumber).filter(PhoneNumber.contact_id == contact_id).all()
    assert len(phones) == 1
    assert phones[0].number == "+1 206-555-0199"
    assert phones[0].source == "ContactOut"

    # Verify Opportunity and M2M Link
    opp = test_db.get(Opportunity, opportunity_id)
    assert opp.title == "VP Engineering / Cloud Architecture"
    assert opp.company_id == company_id

    m2m = test_db.query(OpportunityContact).filter(
        OpportunityContact.opportunity_id == opportunity_id,
        OpportunityContact.contact_id == contact_id,
    ).first()
    assert m2m is not None

    # Verify Audit Log entry
    audit = test_db.query(AuditLog).filter(
        AuditLog.event_type == "prospect_captured",
        AuditLog.entity_id == capture_id,
    ).first()
    assert audit is not None


def test_linkedin_company_page_capture(client, test_db):
    """Verify capturing a company page creates company record without requiring contact."""
    payload = {
        "capture_type": "linkedin_company",
        "page_type": "linkedin_company",
        "source_url": "https://www.linkedin.com/company/innovate-corp",
        "company": {
            "name": "Innovate Corp",
            "website": "https://innovatecorp.example.com",
            "industry": "Enterprise Software",
            "description": "Building modern distributed tools.",
            "type": "client",
        },
    }
    response = client.post("/api/v1/captures/", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 201
    data = response.json()
    assert data["company_id"] is not None
    assert data["contact_id"] is None
    assert data["opportunity_id"] is None

    comp = test_db.get(Company, data["company_id"])
    assert comp.name == "Innovate Corp"
    assert comp.type == "client"


def test_linkedin_job_capture(client, test_db):
    """Verify capturing a job listing creates opportunity and company."""
    payload = {
        "capture_type": "job_listing",
        "page_type": "job_listing",
        "source_url": "https://www.linkedin.com/jobs/view/99887766",
        "company": {
            "name": "Apex Cloud Systems",
            "website": "https://apexcloud.example.com",
            "type": "employer",
        },
        "opportunity": {
            "title": "Senior Cloud SRE",
            "description": "Kubernetes, Terraform, Python, incident management.",
            "type": "employment",
            "source_url": "https://www.linkedin.com/jobs/view/99887766",
        },
    }
    response = client.post("/api/v1/captures/", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 201
    data = response.json()
    assert data["company_id"] is not None
    assert data["opportunity_id"] is not None
    assert data["contact_id"] is None

    opp = test_db.get(Opportunity, data["opportunity_id"])
    assert opp.title == "Senior Cloud SRE"
    assert opp.status == "active"


def test_linkedin_post_capture_with_author_context(client, test_db):
    """Verify capturing a LinkedIn hiring post links author as decision-maker without conflating opportunity."""
    payload = {
        "capture_type": "linkedin_post",
        "page_type": "linkedin_post",
        "source_url": "https://www.linkedin.com/feed/update/urn:li:activity:1234567890",
        "opportunity": {
            "title": "Hiring Platform Engineers",
            "type": "employment",
        },
        "post": {
            "author_name": "Marcus Vance",
            "author_linkedin_url": "https://www.linkedin.com/in/marcus-vance-cto",
            "author_headline": "CTO at Nexus Robotics",
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1234567890",
            "post_text": "We're expanding our robotics cloud team! Hiring 2 Staff Engineers.",
            "post_timestamp": "2h",
            "company_mentioned": "Nexus Robotics",
            "create_author_contact": True,
        },
    }

    response = client.post("/api/v1/captures/", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 201
    data = response.json()
    assert data["post_id"] is not None
    assert data["contact_id"] is not None
    assert data["company_id"] is not None
    assert data["opportunity_id"] is not None

    # Check post record in database
    post_rec = test_db.get(LinkedInPost, data["post_id"])
    assert post_rec is not None
    assert post_rec.author_name == "Marcus Vance"
    assert post_rec.company_mentioned == "Nexus Robotics"
    assert post_rec.author_contact_id == data["contact_id"]
    assert post_rec.opportunity_id == data["opportunity_id"]

    # Verify author contact
    author_contact = test_db.get(Contact, data["contact_id"])
    assert author_contact.first_name == "Marcus"
    assert author_contact.last_name == "Vance"
    assert author_contact.headline == "CTO at Nexus Robotics"

    # Verify author is linked to opportunity
    m2m = test_db.query(OpportunityContact).filter(
        OpportunityContact.opportunity_id == data["opportunity_id"],
        OpportunityContact.contact_id == data["contact_id"],
    ).first()
    assert m2m is not None


def test_capture_idempotent_deduplication_by_linkedin_url(client, test_db):
    """Verify capturing same contact with variation of normalized LinkedIn URL merges without duplicate."""
    # First capture
    payload1 = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/elena-rostova/",
        "contact": {
            "first_name": "Elena",
            "last_name": "Rostova",
            "headline": "Lead Research Scientist",
            "linkedin_url": "https://www.linkedin.com/in/elena-rostova/",
            "emails": [{"address": "elena@biotech.org", "source": "Apollo"}],
        },
        "company": {"name": "BioTech Innovations"},
    }
    r1 = client.post("/api/v1/captures/", json=payload1, headers=AUTH_HEADER)
    assert r1.status_code == 201
    contact_id_1 = r1.json()["contact_id"]

    # Second capture with query parameters and uppercase variation
    payload2 = {
        "capture_type": "linkedin_profile",
        "source_url": "https://linkedin.com/in/ELENA-ROSTOVA?trk=public_profile",
        "contact": {
            "first_name": "Elena",
            "last_name": "Rostova",
            "headline": "Principal Research Scientist",
            "linkedin_url": "https://linkedin.com/in/ELENA-ROSTOVA?trk=public_profile",
            "emails": [{"address": "elena.personal@gmail.com", "source": "ContactOut"}],
        },
        "company": {"name": "BioTech Innovations"},
    }
    r2 = client.post("/api/v1/captures/", json=payload2, headers=AUTH_HEADER)
    assert r2.status_code == 201
    contact_id_2 = r2.json()["contact_id"]

    # Same contact record must be returned
    assert contact_id_1 == contact_id_2
    assert r2.json()["duplicate_flag"] == 0

    # Check database: both emails exist under single contact
    emails = test_db.query(EmailAddress).filter(EmailAddress.contact_id == contact_id_1).all()
    assert len(emails) == 2


def test_capture_duplicate_flag_tertiary_signal_manual_review(client, test_db):
    """Verify name+company match without unique LinkedIn/Email ID match flags duplicate_flag=1 for review."""
    # First contact
    payload1 = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/john-doe-original",
        "contact": {
            "first_name": "John",
            "last_name": "Doe",
            "linkedin_url": "https://www.linkedin.com/in/john-doe-original",
        },
        "company": {"name": "Global Dynamics"},
    }
    r1 = client.post("/api/v1/captures/", json=payload1, headers=AUTH_HEADER)
    assert r1.status_code == 201
    first_id = r1.json()["contact_id"]

    # Second contact with SAME name and SAME company, but DIFFERENT LinkedIn URL
    payload2 = {
        "capture_type": "linkedin_profile",
        "source_url": "https://www.linkedin.com/in/john-doe-different",
        "contact": {
            "first_name": "John",
            "last_name": "Doe",
            "linkedin_url": "https://www.linkedin.com/in/john-doe-different",
        },
        "company": {"name": "Global Dynamics"},
    }
    r2 = client.post("/api/v1/captures/", json=payload2, headers=AUTH_HEADER)
    assert r2.status_code == 201
    second_id = r2.json()["contact_id"]

    # Distinct contact created and flagged for manual review
    assert second_id != first_id
    assert r2.json()["duplicate_flag"] == 1
    assert "flagged as potential duplicate" in r2.json()["message"]

    second_contact = test_db.get(Contact, second_id)
    assert second_contact.duplicate_flag == 1
    assert second_contact.duplicate_of_contact_id == first_id


def test_capture_validation_error_handling(client):
    """Verify invalid payloads (e.g. empty contact first_name) return HTTP 422 Unprocessable Entity."""
    payload = {
        "capture_type": "linkedin_profile",
        "contact": {"first_name": ""},  # min_length=1 constraint
    }
    response = client.post("/api/v1/captures/", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 422
