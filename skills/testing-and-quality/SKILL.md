---
name: testing-and-quality
description: Unit, integration, and end-to-end testing for Tandora — test structure, mocking external services, regression testing, and coverage requirements.
risk: low
source: project
date_added: '2026-11-21'
---

# Testing and Quality Skill — Tandora

## Purpose

This skill covers testing practices for the Tandora application: directory structure, mocking external services, database fixtures, API test patterns, and coverage requirements.

## When to Use

Read this skill before writing any test file in `backend/tests/`. Apply these practices in every milestone.

## Required Engineering Practices

### Test Directory Structure

```
backend/tests/
├── conftest.py           # Shared fixtures (in-memory SQLite, test client, mocks)
├── unit/
│   ├── test_verification_service.py
│   ├── test_draft_service.py
│   ├── test_sending_service.py
│   └── test_inbox_service.py
├── api/
│   ├── test_companies_api.py
│   ├── test_contacts_api.py
│   ├── test_drafts_api.py
│   └── test_sending_api.py
└── integration/
    └── test_outreach_workflow.py
```

### Core Fixtures

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, Base

@pytest.fixture(scope="function")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    @event.listens_for(engine, "connect")
    def set_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def test_db(test_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = Session()
    yield db
    db.close()

@pytest.fixture(scope="function")
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

### Mocking External Services

All external services must be mocked in tests. Never make real HTTP or network requests:

```python
# Mocking Reoon API
from unittest.mock import patch, MagicMock

def test_verify_safe_email(test_db):
    mock_response = {
        "status": "safe",
        "email": "test@example.com",
        "credits_used": 1
    }
    with patch("app.integrations.reoon.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.get.return_value.json.return_value = mock_response
        mock_instance.get.return_value.raise_for_status = MagicMock()
        
        result = verify_email_address(test_db, email_address_id=1)
        assert result.status == "safe"
```

```python
# Mocking Gemini
def test_generate_draft(test_db):
    with patch("app.integrations.gemini.genai.GenerativeModel") as mock_model:
        mock_instance = mock_model.return_value
        mock_instance.generate_content.return_value.text = (
            "SUBJECT: Quick Question on Cloud Architecture\nBODY:\nHi Jane,\nI noticed your open role..."
        )
        draft = generate_draft(test_db, thread_id=1)
        assert draft.subject == "Quick Question on Cloud Architecture"
```

```python
# Mocking Zoho SMTP
def test_send_email(test_db):
    with patch("app.integrations.zoho_smtp.smtplib.SMTP") as mock_smtp:
        mock_instance = mock_smtp.return_value.__enter__.return_value
        mock_instance.sendmail = MagicMock()
        message_id = send_approved_email(test_db, thread_id=1, draft_id=1, approval_id=1)
        assert message_id is not None
```

### Integration Workflow Test

```python
def test_full_outreach_workflow(client, test_db, mock_reoon_safe, mock_gemini, mock_smtp):
    # 1. Capture company
    co_res = client.post("/api/v1/companies", json={"name": "Acme Corp", "type": "employer"})
    company_id = co_res.json()["id"]

    # 2. Add opportunity
    opp_res = client.post(f"/api/v1/companies/{company_id}/opportunities",
                          json={"title": "DevOps Lead", "type": "employment"})
    opp_id = opp_res.json()["id"]

    # 3. Add contact and email
    ct_res = client.post(f"/api/v1/companies/{company_id}/contacts",
                         json={"first_name": "Alice", "last_name": "Smith"})
    contact_id = ct_res.json()["id"]
    em_res = client.post(f"/api/v1/contacts/{contact_id}/emails",
                         json={"address": "alice@acme.com", "is_primary": True})
    email_id = em_res.json()["id"]

    # 4. Verify email
    client.post(f"/api/v1/emails/{email_id}/verify")

    # 5. Create thread and generate draft
    th_res = client.post("/api/v1/outreach-threads",
                         json={"opportunity_id": opp_id, "contact_id": contact_id,
                               "selected_email_address_id": email_id})
    thread_id = th_res.json()["id"]
    dr_res = client.post(f"/api/v1/outreach-threads/{thread_id}/drafts/generate")
    draft_id = dr_res.json()["id"]

    # 6. Approve draft
    app_res = client.post(f"/api/v1/drafts/{draft_id}/approve")
    approval_id = app_res.json()["id"]

    # 7. Send approved email
    send_res = client.post(f"/api/v1/outreach-threads/{thread_id}/send")
    assert send_res.status_code == 200
    assert "message_id" in send_res.json()
```

## Coverage Requirements

- Minimum 80% test coverage across services and integrations.
- 100% test coverage for the pre-send safety checklist in `sending_service.py`.
- 100% test coverage for the approval requirement logic.
- 100% test coverage for catch-all address approval gating.

## Common Mistakes

- Leaking test data across tests by not using isolated transactions or fresh in-memory DBs.
- Writing tests that make actual network calls to Reoon, Zoho, Gemini, or Google Sheets.
- Testing only happy paths and ignoring negative validation and error handling paths.
- Omitting assertions for audit log generation.

## Project-Specific Constraints

- Run tests via `pytest backend/tests/ -v`.
- In-memory SQLite with `PRAGMA foreign_keys=ON` for testing.
- Must verify that unapproved emails reject send calls with HTTP 403.
