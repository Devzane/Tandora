"""Automated tests for Reoon Email Verification, caching lifecycle, and approved policy enforcement."""

from datetime import datetime, timedelta, timezone
import json
import logging
import threading
import time
from unittest.mock import MagicMock, patch

import os
import tempfile

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models import Base

from app.config import MissingCredentialError, Settings
from app.integrations.reoon import ReoonClient, ReoonAPIError
from app.models.contact import Contact
from app.models.email_address import EmailAddress
from app.models.email_verification import EmailVerification
from app.models.audit_log import AuditLog
from app.services.verification_service import (
    DOCUMENTED_POWER_MODE_STATUSES,
    approve_catch_all,
    get_cached_verification,
    get_email_lock_registry,
    get_latest_verification,
    get_verification_stats,
    is_address_usable,
    map_reoon_status,
    verify_email_address,
)


@pytest.fixture
def sample_contact_and_email(test_db):
    """Create a contact with an associated email address."""
    contact = Contact(
        first_name="Jane",
        last_name="Doe",
        full_name="Jane Doe",
        headline="VP Marketing",
    )
    test_db.add(contact)
    test_db.flush()

    email_obj = EmailAddress(
        contact_id=contact.id,
        address="jane.doe@example.com",
        source="manual",
        is_primary=1,
    )
    test_db.add(email_obj)
    test_db.commit()
    test_db.refresh(email_obj)
    return contact, email_obj


# --- 1. ReoonClient Unit Tests & Timeout Handling ---

def test_reoon_client_verify_power_mode():
    """Verify that ReoonClient calls the API with mode=power, email, and key."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "email": "test@example.com",
        "status": "safe",
        "is_safe_to_send": True,
        "credits_used": 1,
    }

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = fake_response

        client = ReoonClient(api_key="test_reoon_key_123", timeout=90.0)
        res = client.verify("test@example.com")

        assert res["status"] == "safe"
        assert res["credits_used"] == 1
        mock_client.get.assert_called_once_with(
            "https://emailverifier.reoon.com/api/v1/verify",
            params={
                "email": "test@example.com",
                "key": "test_reoon_key_123",
                "mode": "power",
            },
        )


def test_reoon_client_configurable_timeout_from_settings():
    """Verify that ReoonClient picks up configurable reoon_timeout_seconds from Settings."""
    with patch("app.integrations.reoon.get_settings") as mock_settings:
        mock_inst = MagicMock()
        mock_inst.validate_reoon_credentials.return_value = "configured_key"
        mock_inst.reoon_timeout_seconds = 120.0
        mock_settings.return_value = mock_inst

        client = ReoonClient()
        assert client.timeout == 120.0
        assert client.api_key == "configured_key"


def test_reoon_client_timeout_recorded_as_technical_failure():
    """Verify that a timeout raises ReoonAPIError indicating timeout without false status."""
    req = httpx.Request("GET", "https://emailverifier.reoon.com/api/v1/verify")
    timeout_error = httpx.ReadTimeout("Read timed out after 90s", request=req)

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = timeout_error

        client = ReoonClient(api_key="test_key", timeout=90.0)
        with pytest.raises(ReoonAPIError) as exc_info:
            client.verify("test@example.com")
        assert "timed out after 90.0s in Power Mode" in str(exc_info.value)


def test_reoon_client_http_error_handling():
    """Verify that HTTP 4xx/5xx responses raise ReoonAPIError."""
    req = httpx.Request("GET", "https://emailverifier.reoon.com/api/v1/verify")
    resp = httpx.Response(status_code=500, request=req)
    http_error = httpx.HTTPStatusError("Server error", request=req, response=resp)

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = http_error

        client = ReoonClient(api_key="test_key")
        with pytest.raises(ReoonAPIError) as exc_info:
            client.verify("test@example.com")
        assert "HTTP 500" in str(exc_info.value)


def test_reoon_client_payload_error_response():
    """Verify that Reoon API payload errors like {'status': 'error', 'reason': '...'} raise ReoonAPIError."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "status": "error",
        "reason": "Insufficient balance credits",
    }

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = fake_response

        client = ReoonClient(api_key="test_key")
        with pytest.raises(ReoonAPIError) as exc_info:
            client.verify("test@example.com")
        assert "Reoon API error: Insufficient balance credits" in str(exc_info.value)


def test_reoon_missing_credentials_raises_actionable_error():
    """Verify that invoking ReoonClient with unconfigured API key raises MissingCredentialError."""
    with patch("app.integrations.reoon.get_settings") as mock_settings:
        mock_inst = MagicMock()
        mock_inst.validate_reoon_credentials.side_effect = MissingCredentialError(
            "Reoon API key is unconfigured. Set REOON_API_KEY in your .env file."
        )
        mock_settings.return_value = mock_inst

        with pytest.raises(MissingCredentialError) as exc_info:
            ReoonClient()
        assert "Set REOON_API_KEY" in str(exc_info.value)


# --- 2. Complete Documented Power Mode Status Mapping ---

def test_map_all_documented_power_mode_statuses():
    """Verify mapping for all 9 documented Reoon Power Mode statuses."""
    expected_mappings = {
        "safe": "safe",
        "invalid": "invalid",
        "disabled": "disabled",
        "disposable": "disposable",
        "inbox_full": "inbox_full",
        "catch_all": "catch-all",
        "role_account": "role_account",
        "spamtrap": "spamtrap",
        "unknown": "unknown",
    }
    for raw, canonical in expected_mappings.items():
        mapped, is_unexpected = map_reoon_status(raw)
        assert mapped == canonical
        assert is_unexpected is False


def test_map_unexpected_status_safely_handled():
    """Verify that undocumented/unexpected statuses (e.g. valid, risky, arbitrary) are mapped safely to unknown."""
    # Reoon Power mode does NOT document valid or risky; they must be handled explicitly as unexpected
    unexpected_statuses = ["valid", "risky", "arbitrary_xyz", "", None]
    for raw in unexpected_statuses:
        mapped, is_unexpected = map_reoon_status(raw)
        assert mapped == "unknown"
        assert is_unexpected is True


# --- 3. Approved Email Verification Policy Tests ---

def test_automatic_catch_all_approval(test_db, sample_contact_and_email):
    """Test that catch_all addresses are automatically approved without requiring manual approval."""
    _, email_obj = sample_contact_and_email

    mock_client = MagicMock()
    mock_client.verify.return_value = {
        "status": "catch_all",
        "is_safe_to_send": True,
        "is_catch_all": True,
        "credits_used": 1,
    }

    v, was_cached = verify_email_address(test_db, email_obj.id, force=False, client=mock_client)
    assert was_cached is False
    assert v.status == "catch-all"
    assert v.catch_all_approved == 1
    assert v.catch_all_approved_at is not None

    test_db.refresh(email_obj)
    assert email_obj.suppressed == 0

    usable, reason = is_address_usable(test_db, email_obj.id)
    assert usable is True
    assert reason == "catch-all"


def test_automatic_role_account_approval(test_db, sample_contact_and_email):
    """Test that role_account addresses are automatically approved without manual gating."""
    _, email_obj = sample_contact_and_email

    mock_client = MagicMock()
    mock_client.verify.return_value = {
        "status": "role_account",
        "is_role_account": True,
        "credits_used": 1,
    }

    v, was_cached = verify_email_address(test_db, email_obj.id, force=False, client=mock_client)
    assert was_cached is False
    assert v.status == "role_account"

    test_db.refresh(email_obj)
    assert email_obj.suppressed == 0

    usable, reason = is_address_usable(test_db, email_obj.id)
    assert usable is True
    assert reason == "role_account"


def test_automatic_suppression_on_invalid_unknown_disposable_spamtrap_disabled(test_db, sample_contact_and_email):
    """Test automatic suppression for all definitive failure statuses."""
    _, email_obj = sample_contact_and_email

    suppress_statuses = ["invalid", "unknown", "disposable", "spamtrap", "disabled"]
    for raw_status in suppress_statuses:
        email_obj.suppressed = 0
        email_obj.suppressed_reason = None
        test_db.commit()

        mock_client = MagicMock()
        mock_client.verify.return_value = {
            "status": raw_status,
            "credits_used": 0 if raw_status == "unknown" else 1,
        }

        v, _ = verify_email_address(test_db, email_obj.id, force=True, client=mock_client)
        test_db.refresh(email_obj)

        assert email_obj.suppressed == 1
        assert f"Reoon verification: {v.status}" in email_obj.suppressed_reason

        usable, reason = is_address_usable(test_db, email_obj.id)
        assert usable is False
        assert "suppressed" in reason.lower()


def test_explicit_inbox_full_suppression_handling(test_db, sample_contact_and_email):
    """Test that inbox_full is suppressed pending an explicitly defined recovery policy."""
    _, email_obj = sample_contact_and_email

    mock_client = MagicMock()
    mock_client.verify.return_value = {
        "status": "inbox_full",
        "has_inbox_full": True,
        "credits_used": 1,
    }

    v, was_cached = verify_email_address(test_db, email_obj.id, force=False, client=mock_client)
    assert v.status == "inbox_full"

    test_db.refresh(email_obj)
    assert email_obj.suppressed == 1
    assert "inbox_full (mailbox full, recovery pending)" in email_obj.suppressed_reason

    usable, reason = is_address_usable(test_db, email_obj.id)
    assert usable is False


def test_unexpected_status_automatically_suppressed(test_db, sample_contact_and_email):
    """Test that unexpected provider responses are treated safely as unknown and suppressed."""
    _, email_obj = sample_contact_and_email

    mock_client = MagicMock()
    mock_client.verify.return_value = {
        "status": "unrecognized_provider_flag_99",
        "credits_used": 0,
    }

    v, _ = verify_email_address(test_db, email_obj.id, force=True, client=mock_client)
    assert v.status == "unknown"

    test_db.refresh(email_obj)
    assert email_obj.suppressed == 1
    assert "unexpected status 'unrecognized_provider_flag_99'" in email_obj.suppressed_reason

    usable, _ = is_address_usable(test_db, email_obj.id)
    assert usable is False


# --- 4. Technical Failure & Isolation Tests ---

def test_no_accidental_suppression_or_record_on_timeout(test_db, sample_contact_and_email):
    """Verify that a timeout does NOT insert any verification record or alter email suppression."""
    _, email_obj = sample_contact_and_email
    assert email_obj.suppressed == 0

    mock_client = MagicMock()
    mock_client.verify.side_effect = ReoonAPIError("Reoon API request timed out after 90.0s in Power Mode")

    with pytest.raises(ReoonAPIError) as exc_info:
        verify_email_address(test_db, email_obj.id, force=False, client=mock_client)
    assert "timed out" in str(exc_info.value)

    # Database state must remain pristine
    test_db.refresh(email_obj)
    assert email_obj.suppressed == 0
    assert email_obj.suppressed_reason is None

    # No verification record created
    count = test_db.scalar(EmailVerification.__table__.select().where(EmailVerification.email_address_id == email_obj.id))
    assert count is None


def test_no_accidental_suppression_or_record_on_http_error(test_db, sample_contact_and_email):
    """Verify that an HTTP 502/500 does NOT insert verification record or alter suppression."""
    _, email_obj = sample_contact_and_email

    mock_client = MagicMock()
    mock_client.verify.side_effect = ReoonAPIError("Reoon API returned HTTP 502")

    with pytest.raises(ReoonAPIError):
        verify_email_address(test_db, email_obj.id, force=False, client=mock_client)

    test_db.refresh(email_obj)
    assert email_obj.suppressed == 0
    assert get_latest_verification(test_db, email_obj.id) is None


# --- 5. Credit Accounting Tests ---

def test_credit_accounting_conclusive_vs_unknown(test_db, sample_contact_and_email):
    """Test credit accounting: conclusive consumes 1 credit, unknown consumes 0 (auto-refunded)."""
    _, email_obj = sample_contact_and_email

    mock_client = MagicMock()

    # 1. Conclusive status without explicit credits_used -> defaults to 1 credit
    mock_client.verify.return_value = {"status": "safe"}
    v_safe, _ = verify_email_address(test_db, email_obj.id, force=True, client=mock_client)
    assert v_safe.credits_used == 1

    # 2. Unknown status without explicit credits_used -> defaults to 0 credits (Reoon refund)
    mock_client.verify.return_value = {"status": "unknown"}
    v_unk, _ = verify_email_address(test_db, email_obj.id, force=True, client=mock_client)
    assert v_unk.credits_used == 0

    # 3. Explicit credits_used returned by Reoon is preserved
    mock_client.verify.return_value = {"status": "safe", "credits_used": 2}
    v_exp, _ = verify_email_address(test_db, email_obj.id, force=True, client=mock_client)
    assert v_exp.credits_used == 2

    # Stats reconciliation
    stats = get_verification_stats(test_db)
    assert stats["total_credits_used"] == 3  # 1 + 0 + 2
    assert stats["total_verifications"] == 3


# --- 6. Caching Lifecycle Tests ---

def test_30_day_caching_lifecycle(test_db, sample_contact_and_email):
    """Test that repeat verification within 30 days returns cached record with 0 extra API calls."""
    _, email_obj = sample_contact_and_email

    mock_client = MagicMock()
    mock_client.verify.return_value = {
        "status": "safe",
        "is_safe_to_send": True,
        "credits_used": 1,
    }

    # 1. First verification
    v1, was_cached = verify_email_address(test_db, email_obj.id, force=False, client=mock_client)
    assert was_cached is False
    assert v1.status == "safe"
    assert mock_client.verify.call_count == 1

    # 2. Second verification within 30 days -> cache hit
    v2, was_cached2 = verify_email_address(test_db, email_obj.id, force=False, client=mock_client)
    assert was_cached2 is True
    assert v2.id == v1.id
    assert mock_client.verify.call_count == 1

    # 3. Forced re-verification -> cache bypass
    v3, was_cached3 = verify_email_address(test_db, email_obj.id, force=True, client=mock_client)
    assert was_cached3 is False
    assert v3.id != v1.id
    assert mock_client.verify.call_count == 2


def test_expired_cache_triggers_fresh_verification(test_db, sample_contact_and_email):
    """Test that a verification record older than 30 days is expired and triggers fresh call."""
    _, email_obj = sample_contact_and_email

    old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=35)
    expired_time = old_time + timedelta(days=30)
    expired_record = EmailVerification(
        email_address_id=email_obj.id,
        status="safe",
        catch_all_approved=0,
        credits_used=1,
        verified_at=old_time,
        expires_at=expired_time,
    )
    test_db.add(expired_record)
    test_db.commit()

    assert get_cached_verification(test_db, email_obj.id) is None

    mock_client = MagicMock()
    mock_client.verify.return_value = {"status": "safe", "credits_used": 1}

    v_new, was_cached = verify_email_address(test_db, email_obj.id, force=False, client=mock_client)
    assert was_cached is False
    assert v_new.id != expired_record.id
    assert mock_client.verify.call_count == 1


# --- 7. REST API & UI Integration Tests ---

def test_api_verify_endpoint_success_and_cache(client, test_db, sample_contact_and_email):
    """Test POST /api/v1/emails/{id}/verify returns 200 and reflects approved policy."""
    _, email_obj = sample_contact_and_email

    with patch("app.api.v1.email_verification.verify_email_address") as mock_verify:
        fake_v = EmailVerification(
            id=42,
            email_address_id=email_obj.id,
            status="safe",
            catch_all_approved=0,
            credits_used=1,
            verified_at=datetime.now(timezone.utc).replace(tzinfo=None),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
        )
        mock_verify.return_value = (fake_v, False)

        resp = client.post(f"/api/v1/emails/{email_obj.id}/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "safe"
        assert data["was_cached"] is False
        assert data["email_address_id"] == email_obj.id


def test_api_verification_stats_endpoint(client, test_db):
    """Test GET /api/v1/verifications/stats returns aggregated metrics."""
    resp = client.get("/api/v1/verifications/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_verifications" in data
    assert "total_credits_used" in data
    assert "suppressed_by_verification" in data


def test_ui_email_verify_route_redirects(client, test_db, sample_contact_and_email):
    """Test UI verify POST handler redirects to contact detail."""
    contact, email_obj = sample_contact_and_email

    with patch("app.ui.routes.verify_email_address") as mock_verify:
        fake_v = EmailVerification(
            id=1,
            email_address_id=email_obj.id,
            status="safe",
            catch_all_approved=0,
            credits_used=1,
            verified_at=datetime.now(timezone.utc).replace(tzinfo=None),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
        )
        mock_verify.return_value = (fake_v, False)

        resp = client.post(
            f"/contacts/{contact.id}/emails/{email_obj.id}/verify",
            data={"force": 0},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/contacts/{contact.id}"


# --- 7. Concurrency & Mutex Regression Tests ---

def test_concurrent_verifications_same_email_executes_single_provider_call(test_engine, sample_contact_and_email):
    """Verify that concurrent requests for the same email execute exactly one provider HTTP call.

    The second request waits on the keyed mutex and reuses the newly committed result.
    """
    _, email_obj = sample_contact_and_email
    SessionMaker = sessionmaker(bind=test_engine)

    call_count = 0
    call_lock = threading.Lock()

    class SlowMockReoonClient:
        def verify(self, address: str):
            nonlocal call_count
            with call_lock:
                call_count += 1
            # Simulate a realistic slow network check
            time.sleep(0.15)
            return {
                "status": "safe",
                "email": address,
                "is_safe_to_send": True,
                "credits_used": 1,
            }

    mock_client = SlowMockReoonClient()
    results = [None, None]
    errors = [None, None]

    def run_verify(idx: int):
        session = SessionMaker()
        try:
            v, was_cached = verify_email_address(session, email_obj.id, force=False, client=mock_client)
            results[idx] = (v.id, v.status, was_cached)
        except Exception as e:
            errors[idx] = e
        finally:
            session.close()

    t1 = threading.Thread(target=run_verify, args=(0,))
    t2 = threading.Thread(target=run_verify, args=(1,))

    t1.start()
    time.sleep(0.02)  # Ensure t1 acquires the lock first
    t2.start()

    t1.join()
    t2.join()

    assert errors[0] is None, f"Thread 0 raised error: {errors[0]}"
    assert errors[1] is None, f"Thread 1 raised error: {errors[1]}"

    # Exactly ONE provider call must occur
    assert call_count == 1

    # Thread 0 performed the actual call (was_cached=False)
    # Thread 1 reused the committed result (was_cached=True)
    r1 = results[0]
    r2 = results[1]
    assert r1 is not None and r2 is not None
    assert r1[1] == "safe"
    assert r2[1] == "safe"
    assert r1[0] == r2[0]  # Both point to the exact same verification record id
    assert (r1[2], r2[2]) == (False, True)


def test_concurrent_verifications_different_emails_execute_independently():
    """Verify that different email addresses can be verified independently without mutual blocking."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    file_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    with file_engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.commit()

    Base.metadata.create_all(file_engine)
    SessionMaker = sessionmaker(bind=file_engine)

    init_session = SessionMaker()
    contact = Contact(first_name="Alice", last_name="Smith", full_name="Alice Smith")
    init_session.add(contact)
    init_session.flush()

    e1 = EmailAddress(contact_id=contact.id, address="e1@example.com", source="manual")
    e2 = EmailAddress(contact_id=contact.id, address="e2@example.com", source="manual")
    init_session.add_all([e1, e2])
    init_session.commit()
    e1_id, e2_id = e1.id, e2.id
    init_session.close()

    active_calls = 0
    max_concurrent_calls = 0
    call_lock = threading.Lock()
    barrier = threading.Barrier(2, timeout=5.0)

    class ConcurrentMockClient:
        def verify(self, address: str):
            nonlocal active_calls, max_concurrent_calls
            with call_lock:
                active_calls += 1
                if active_calls > max_concurrent_calls:
                    max_concurrent_calls = active_calls
            # Barrier guarantees both threads reach verify() concurrently
            barrier.wait()
            with call_lock:
                active_calls -= 1
            return {"status": "safe", "email": address, "credits_used": 1}

    mock_client = ConcurrentMockClient()
    results = [None, None]
    errors = [None, None]

    def verify_worker(idx: int, email_id: int):
        s = SessionMaker()
        try:
            v, was_cached = verify_email_address(s, email_id, force=False, client=mock_client)
            results[idx] = (v.status, was_cached)
        except Exception as e:
            errors[idx] = e
        finally:
            s.close()

    try:
        t1 = threading.Thread(target=verify_worker, args=(0, e1_id))
        t2 = threading.Thread(target=verify_worker, args=(1, e2_id))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors[0] is None, f"Thread 0 error: {errors[0]}"
        assert errors[1] is None, f"Thread 1 error: {errors[1]}"
        assert results[0] == ("safe", False)
        assert results[1] == ("safe", False)
        assert max_concurrent_calls == 2  # Proves both addresses executed concurrently
    finally:
        file_engine.dispose()
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def test_failed_first_verification_releases_lock_and_allows_subsequent_attempts(test_db, sample_contact_and_email):
    """Verify that a technical failure properly releases the lock and does not block retries."""
    _, email_obj = sample_contact_and_email

    failing_client = MagicMock()
    failing_client.verify.side_effect = ReoonAPIError("Reoon API returned HTTP 502")

    with pytest.raises(ReoonAPIError):
        verify_email_address(test_db, email_obj.id, force=False, client=failing_client)

    # Verify lock registry is clean
    registry = get_email_lock_registry()
    assert registry.active_lock_count() == 0

    # A subsequent attempt succeeds when provider recovers
    recovering_client = MagicMock()
    recovering_client.verify.return_value = {"status": "safe", "credits_used": 1}

    v, was_cached = verify_email_address(test_db, email_obj.id, force=False, client=recovering_client)
    assert v.status == "safe"
    assert was_cached is False


def test_lock_registry_safe_lifecycle_and_cleanup(test_db, sample_contact_and_email):
    """Verify that lock registry entries are automatically pruned, avoiding unbounded memory growth."""
    _, email_obj = sample_contact_and_email
    registry = get_email_lock_registry()

    assert registry.active_lock_count() == 0

    mock_client = MagicMock()
    mock_client.verify.return_value = {"status": "safe", "credits_used": 1}

    verify_email_address(test_db, email_obj.id, force=False, client=mock_client)

    # After completion, the lock entry for email_obj.id must be pruned
    assert registry.active_lock_count() == 0


# --- 8. Reoon Credential Protection Regression Tests ---

@pytest.mark.parametrize("status_code", [401, 403, 500])
def test_reoon_http_errors_do_not_leak_api_key_in_logs_or_exceptions(status_code, caplog):
    """Verify that HTTP 401/403/500 responses do NOT expose the API key in logs, exceptions, or tracebacks."""
    secret_key = "REOON_SECRET_KEY_EXPOSURE_TEST_98765"
    req_url = f"https://emailverifier.reoon.com/api/v1/verify?email=test%40example.com&key={secret_key}&mode=power"
    req = httpx.Request("GET", req_url)
    resp = httpx.Response(status_code=status_code, request=req, text=f"HTTP Error {status_code}")
    http_error = httpx.HTTPStatusError(f"Client error '{status_code}'", request=req, response=resp)

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = http_error

        client = ReoonClient(api_key=secret_key)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ReoonAPIError) as exc_info:
                client.verify("test@example.com")

        # 1. Secret key must NOT be in exception message
        assert secret_key not in str(exc_info.value)
        assert f"HTTP {status_code}" in str(exc_info.value)

        # 2. Secret key must NOT be in chained exception context (__cause__ / __context__)
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__context__ is None

        # 3. Secret key must NOT be in application logs
        assert secret_key not in caplog.text
        # Log should mention the HTTP status cleanly
        assert f"HTTP status {status_code}" in caplog.text


def test_reoon_timeout_does_not_leak_api_key_in_logs_or_exceptions(caplog):
    """Verify that timeouts do not leak credentials in exception message, logs, or tracebacks."""
    secret_key = "REOON_SECRET_KEY_TIMEOUT_12345"
    req_url = f"https://emailverifier.reoon.com/api/v1/verify?email=test%40example.com&key={secret_key}&mode=power"
    req = httpx.Request("GET", req_url)
    timeout_error = httpx.ReadTimeout("Read timed out", request=req)

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = timeout_error

        client = ReoonClient(api_key=secret_key, timeout=90.0)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ReoonAPIError) as exc_info:
                client.verify("test@example.com")

        assert secret_key not in str(exc_info.value)
        assert secret_key not in caplog.text
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__context__ is None
        assert "timed out after 90.0s in Power Mode" in str(exc_info.value)


def test_reoon_connection_error_does_not_leak_api_key_in_logs_or_exceptions(caplog):
    """Verify that connection/network errors do not leak credentials in exception message, logs, or tracebacks."""
    secret_key = "REOON_SECRET_KEY_CONNECT_12345"
    req_url = f"https://emailverifier.reoon.com/api/v1/verify?email=test%40example.com&key={secret_key}&mode=power"
    req = httpx.Request("GET", req_url)
    connect_error = httpx.ConnectError("Connection refused", request=req)

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = connect_error

        client = ReoonClient(api_key=secret_key)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ReoonAPIError) as exc_info:
                client.verify("test@example.com")

        assert secret_key not in str(exc_info.value)
        assert secret_key not in caplog.text
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__context__ is None
        assert "Could not connect to Reoon API: ConnectError" in str(exc_info.value)


def test_reoon_payload_error_reason_sanitization(caplog):
    """Verify that provider error response reasons containing API keys or URLs are thoroughly sanitized."""
    secret_key = "REOON_SECRET_KEY_IN_REASON_9999"
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "status": "error",
        "reason": f"Request failed for https://emailverifier.reoon.com/api/v1/verify?key={secret_key}&email=test@example.com with key={secret_key}",
    }

    with patch("app.integrations.reoon.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = fake_response

        client = ReoonClient(api_key=secret_key)

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ReoonAPIError) as exc_info:
                client.verify("test@example.com")

        # Must not contain API key
        assert secret_key not in str(exc_info.value)
        assert secret_key not in caplog.text
        # Must not contain the full URL with query params
        assert "https://emailverifier.reoon.com" not in str(exc_info.value)
        assert "https://emailverifier.reoon.com" not in caplog.text
        assert "[REDACTED_URL]" in str(exc_info.value)
        assert "[REDACTED]" in str(exc_info.value)


# --- 9. Forced Verification Semantics & Edge Cases ---

def test_concurrent_forced_verifications_same_email_both_execute_sequentially(test_engine, sample_contact_and_email):
    """Verify that when two simultaneous requests explicitly pass force=True, both execute sequentially.

    Because both explicitly requested a forced cache bypass, both obtain fresh verifications sequentially
    under mutex serialization without data corruption or lost updates.
    """
    _, email_obj = sample_contact_and_email
    SessionMaker = sessionmaker(bind=test_engine)

    call_count = 0
    call_lock = threading.Lock()

    class CountingMockReoonClient:
        def verify(self, address: str):
            nonlocal call_count
            with call_lock:
                call_count += 1
            time.sleep(0.1)
            return {"status": "safe", "email": address, "credits_used": 1}

    mock_client = CountingMockReoonClient()
    results = [None, None]
    errors = [None, None]

    def forced_worker(idx: int):
        s = SessionMaker()
        try:
            v, was_cached = verify_email_address(s, email_obj.id, force=True, client=mock_client)
            results[idx] = (v.id, v.status, was_cached)
        except Exception as e:
            errors[idx] = e
        finally:
            s.close()

    t1 = threading.Thread(target=forced_worker, args=(0,))
    t2 = threading.Thread(target=forced_worker, args=(1,))

    t1.start()
    time.sleep(0.02)
    t2.start()

    t1.join()
    t2.join()

    assert errors[0] is None, f"Thread 0 error: {errors[0]}"
    assert errors[1] is None, f"Thread 1 error: {errors[1]}"

    # Because both threads explicitly specified force=True, both executed sequentially
    assert call_count == 2
    assert results[0][2] is False
    assert results[1][2] is False
    # The two records are distinct sequential verifications
    assert results[0][0] != results[1][0]


def test_normal_request_waiting_behind_forced_request_reuses_committed_result(test_engine, sample_contact_and_email):
    """Verify that a normal request (force=False) waiting behind a forced request (force=True) reuses the result."""
    _, email_obj = sample_contact_and_email
    SessionMaker = sessionmaker(bind=test_engine)

    call_count = 0
    call_lock = threading.Lock()

    class SlowMockClient:
        def verify(self, address: str):
            nonlocal call_count
            with call_lock:
                call_count += 1
            time.sleep(0.15)
            return {"status": "safe", "email": address, "credits_used": 1}

    mock_client = SlowMockClient()
    results = [None, None]
    errors = [None, None]

    def worker_forced(idx: int):
        s = SessionMaker()
        try:
            v, was_cached = verify_email_address(s, email_obj.id, force=True, client=mock_client)
            results[idx] = (v.id, v.status, was_cached)
        except Exception as e:
            errors[idx] = e
        finally:
            s.close()

    def worker_normal(idx: int):
        s = SessionMaker()
        try:
            v, was_cached = verify_email_address(s, email_obj.id, force=False, client=mock_client)
            results[idx] = (v.id, v.status, was_cached)
        except Exception as e:
            errors[idx] = e
        finally:
            s.close()

    t1 = threading.Thread(target=worker_forced, args=(0,))
    t2 = threading.Thread(target=worker_normal, args=(1,))

    t1.start()
    time.sleep(0.02)  # Ensure t1 (forced) acquires the lock first
    t2.start()

    t1.join()
    t2.join()

    assert errors[0] is None, f"Thread 0 error: {errors[0]}"
    assert errors[1] is None, f"Thread 1 error: {errors[1]}"

    # Only ONE provider call must occur
    assert call_count == 1
    # Thread 0 (forced) performed the call
    assert results[0][2] is False
    # Thread 1 (normal) waited and reused Thread 0's committed result
    assert results[1][2] is True
    assert results[0][0] == results[1][0]


def test_failed_forced_verification_preserves_existing_valid_cache(test_db, sample_contact_and_email):
    """Verify that a failed forced verification leaves existing valid cache intact and does not corrupt state."""
    _, email_obj = sample_contact_and_email

    # 1. Establish an existing valid verification
    successful_client = MagicMock()
    successful_client.verify.return_value = {"status": "safe", "credits_used": 1}
    v_initial, _ = verify_email_address(test_db, email_obj.id, force=False, client=successful_client)
    assert v_initial.status == "safe"

    # 2. Attempt a forced re-verification that fails
    failing_client = MagicMock()
    failing_client.verify.side_effect = ReoonAPIError("Reoon API returned HTTP 502")

    with pytest.raises(ReoonAPIError):
        verify_email_address(test_db, email_obj.id, force=True, client=failing_client)

    test_db.rollback()

    # 3. Assert existing verification remains cached and valid
    cached = get_cached_verification(test_db, email_obj.id)
    assert cached is not None
    assert cached.id == v_initial.id
    assert cached.status == "safe"

    # 4. Assert address is still active and usable
    test_db.refresh(email_obj)
    assert email_obj.suppressed == 0
    usable, reason = is_address_usable(test_db, email_obj.id)
    assert usable is True
    assert reason == "safe"
