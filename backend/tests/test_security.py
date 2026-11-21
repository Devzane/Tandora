"""Tests for local browser security: CSRF defense, Origin verification, and secure headers."""

from app.schemas.company import CompanyCreate
from app.schemas.contact import ContactCreate
from app.services.organization_service import create_company
from app.services.contact_service import create_contact


def test_cross_origin_state_changing_request_blocked(client, test_db):
    """Verify state-changing POST from malicious origin is rejected with 403 Forbidden."""
    company = create_company(test_db, CompanyCreate(name="Safe Corp"))
    test_db.commit()

    # Attempt cross-origin POST with external Origin header
    response = client.post(
        f"/organizations/{company.id}/suppress",
        data={"suppressed": 1, "reason": "Attack"},
        headers={"Origin": "https://malicious-tracker.evil.com"},
    )
    assert response.status_code == 403
    assert "Cross-origin request from" in response.json()["detail"]

    # Verify company was NOT suppressed
    test_db.refresh(company)
    assert company.suppressed == 0


def test_sec_fetch_site_cross_site_blocked(client, test_db):
    """Verify modern browser Sec-Fetch-Site: cross-site header is rejected."""
    company = create_company(test_db, CompanyCreate(name="Target Org"))
    test_db.commit()

    response = client.post(
        f"/organizations/{company.id}/suppress",
        data={"suppressed": 1, "reason": "Attack"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403
    assert "Cross-site state-changing requests are prohibited" in response.json()["detail"]


def test_cross_origin_referer_blocked(client, test_db):
    """Verify external Referer header without Origin is rejected."""
    company = create_company(test_db, CompanyCreate(name="Target Org 2"))
    test_db.commit()

    response = client.post(
        f"/organizations/{company.id}/suppress",
        data={"suppressed": 1, "reason": "Attack"},
        headers={"Referer": "https://phishing-site.com/fake-portal"},
    )
    assert response.status_code == 403
    assert "Cross-origin referer" in response.json()["detail"]


def test_allowed_local_origin_accepted(client, test_db):
    """Verify requests originating from local 127.0.0.1 or localhost are accepted."""
    company = create_company(test_db, CompanyCreate(name="Local Valid Org"))
    test_db.commit()

    response = client.post(
        f"/organizations/{company.id}/suppress",
        data={"suppressed": 1, "reason": "Legitimate local action"},
        headers={"Origin": "http://127.0.0.1:8000"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    test_db.refresh(company)
    assert company.suppressed == 1


def test_untrusted_host_header_rejected(client):
    """Verify DNS rebinding attacks using untrusted Host headers are rejected."""
    response = client.get("/", headers={"Host": "evil-rebinding.com"})
    assert response.status_code == 400
    assert "Host 'evil-rebinding.com' is not permitted" in response.json()["detail"]


def test_security_headers_present_on_responses(client):
    """Verify security hardening headers are attached to HTTP responses."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_html_autoescaping_prevents_xss(client, test_db):
    """Verify user-provided content with script tags is properly escaped by Jinja2."""
    xss_payload = "<script>alert('xss')</script>"
    contact, _ = create_contact(
        test_db,
        ContactCreate(
            first_name="Alice",
            last_name=xss_payload,
            headline=xss_payload,
            notes=xss_payload,
        ),
    )
    test_db.commit()

    response = client.get(f"/contacts/{contact.id}")
    assert response.status_code == 200
    # The raw unescaped tag must NOT appear in HTML
    assert "<script>alert('xss')</script>" not in response.text
    # Escaped version should be present
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in response.text or "&lt;script&gt;" in response.text
