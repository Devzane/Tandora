"""Automated tests for Stage 4 Task 3: Thread Initialization, Draft Persistence, Versioning, and Audit Logging."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import sqlite3
import tempfile
import threading
from unittest.mock import MagicMock, patch

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import MissingCredentialError, Settings, get_settings
from app.database import ensure_audit_log_triggers
from app.models import Base
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.contact import Contact
from app.models.draft import Draft
from app.models.email_address import EmailAddress
from app.models.email_verification import EmailVerification
from app.models.opportunity import Opportunity
from app.models.outreach_thread import OutreachThread
from app.providers.llm_interface import DraftResult, LLMGenerationError
from app.services.draft_service import (
    DraftValidationError,
    OutreachEligibilityError,
    ThreadConflictError,
    generate_and_persist_draft,
    get_draft,
    get_draft_lock_registry,
    get_latest_draft,
    get_outreach_thread,
    initialize_outreach_thread,
    list_draft_versions,
)


def _valid_body(marker: str = "warehouse robotics telemetry") -> str:
    return (
        f"Hi Maya, your engineering team's work on {marker} stands out.\n\n"
        "As deployment fleets scale across sites, keeping telemetry pipelines reliable can become challenging.\n\n"
        "I have built resilient Python observability systems and would welcome a brief conversation."
    )


def _valid_json_payload(
    subject: str = "Scaling telemetry reliability",
    marker: str = "warehouse robotics telemetry",
) -> str:
    return json.dumps({"subject": subject, "body": _valid_body(marker)})


def _seed_verified_prospect(
    db,
    *,
    verification_status: str = "safe",
    verified: bool = True,
    expired: bool = False,
    contact_suppressed: int = 0,
    opp_company_suppressed: int = 0,
    contact_company_suppressed: int = 0,
    separate_contact_company: bool = False,
    email_suppressed: int = 0,
    email_address: str = "maya.lin@vectorrobotics.example.com",
    notes: str = "CONFIDENTIAL_CONTACT_NOTE_FOR_TEST",
):
    opp_company = Company(
        name="Vector Robotics",
        industry="Robotics",
        description="Autonomous industrial automation systems.",
        website="https://vectorrobotics.example.com",
        type="freelance_prospect",
        suppressed=opp_company_suppressed,
    )
    db.add(opp_company)
    db.flush()

    contact_company = opp_company
    if separate_contact_company:
        contact_company = Company(
            name="Partner Recruiting LLC",
            industry="Staffing",
            type="employer",
            suppressed=contact_company_suppressed,
        )
        db.add(contact_company)
        db.flush()

    opportunity = Opportunity(
        company_id=opp_company.id,
        type="freelance_prospect",
        title="Platform Infrastructure Consultant",
        description="Improve telemetry pipeline reliability.",
        source_url="https://vectorrobotics.example.com/jobs/1",
    )
    db.add(opportunity)
    db.flush()

    contact = Contact(
        company_id=contact_company.id,
        first_name="Maya",
        last_name="Lin",
        full_name="Maya Lin",
        headline="VP of Engineering",
        notes=notes,
        suppressed=contact_suppressed,
    )
    db.add(contact)
    db.flush()

    email_obj = EmailAddress(
        contact_id=contact.id,
        address=email_address,
        is_primary=1,
        source="manual",
        suppressed=email_suppressed,
    )
    db.add(email_obj)
    db.flush()

    if verified:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        verified_at = now - timedelta(days=40) if expired else now - timedelta(days=1)
        expires_at = now - timedelta(days=10) if expired else now + timedelta(days=29)
        verification = EmailVerification(
            email_address_id=email_obj.id,
            status=verification_status,
            catch_all_approved=1 if verification_status == "catch-all" else 0,
            catch_all_approved_at=verified_at if verification_status == "catch-all" else None,
            credits_used=0 if verification_status == "unknown" else 1,
            verified_at=verified_at,
            expires_at=expires_at,
        )
        db.add(verification)

    db.commit()
    return opp_company, contact_company, opportunity, contact, email_obj


class _StubProvider:
    def __init__(self, responses: list[str | Exception], provider: str = "gemini", model: str = "gemini-3.5-flash-lite"):
        self._responses = list(responses)
        self.provider = provider
        self.model = model
        self.prompts_seen: list[str] = []

    def generate(self, prompt: str) -> DraftResult:
        self.prompts_seen.append(prompt)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return DraftResult(text=item, provider=self.provider, model=self.model, raw_prompt=prompt)


# ==============================================================================
# 1-10. Thread Initialization & Recipient Eligibility Tests
# ==============================================================================


def test_initialize_outreach_thread_success(test_db):
    """1. Valid opportunity, contact, and verified email initialize an OutreachThread."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db, verification_status="safe")

    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    assert thread.id is not None
    assert thread.opportunity_id == opp.id
    assert thread.contact_id == contact.id
    assert thread.selected_email_address_id == email_obj.id
    assert thread.status == "draft"

    logs = test_db.execute(
        select(AuditLog).where(
            AuditLog.event_type == "outreach_thread_created",
            AuditLog.entity_id == thread.id,
        )
    ).scalars().all()
    assert len(logs) == 1


def test_initialize_outreach_thread_idempotent_same_recipient(test_db):
    """2. Repeating initialization with the same recipient returns the existing thread idempotently."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)

    first = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)
    second = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    assert second.id == first.id
    assert second.selected_email_address_id == email_obj.id
    assert test_db.query(OutreachThread).count() == 1
    assert (
        test_db.query(AuditLog).filter(AuditLog.event_type == "outreach_thread_created").count() == 1
    )


def test_initialize_outreach_thread_conflicting_recipient_rejected_and_unchanged(test_db):
    """3-4. Conflicting email selection raises ThreadConflictError and leaves existing recipient untouched."""
    _, _, opp, contact, email_1 = _seed_verified_prospect(
        test_db,
        email_address="maya.primary@vectorrobotics.example.com",
    )
    email_2 = EmailAddress(
        contact_id=contact.id,
        address="maya.alt@vectorrobotics.example.com",
        is_primary=0,
        source="Apollo",
    )
    test_db.add(email_2)
    test_db.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    test_db.add(
        EmailVerification(
            email_address_id=email_2.id,
            status="safe",
            verified_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    test_db.commit()

    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_1.id)

    with pytest.raises(ThreadConflictError, match="already exists"):
        initialize_outreach_thread(test_db, opp.id, contact.id, email_2.id)

    test_db.expire_all()
    persisted = test_db.get(OutreachThread, thread.id)
    assert persisted is not None
    assert persisted.selected_email_address_id == email_1.id


def test_initialize_outreach_thread_missing_entities_rejected(test_db):
    """5. Invalid opportunity, contact, or email IDs raise ValueError."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)

    with pytest.raises(ValueError, match="Opportunity 99999 not found"):
        initialize_outreach_thread(test_db, 99999, contact.id, email_obj.id)

    with pytest.raises(ValueError, match="Contact 99999 not found"):
        initialize_outreach_thread(test_db, opp.id, 99999, email_obj.id)

    with pytest.raises(ValueError, match="EmailAddress 99999 not found"):
        initialize_outreach_thread(test_db, opp.id, contact.id, 99999)


def test_initialize_outreach_thread_rejects_email_owned_by_other_contact(test_db):
    """6. Selected email address must belong to the target contact."""
    opp_company, _, opp, contact_1, _ = _seed_verified_prospect(test_db)

    other_contact = Contact(
        company_id=opp_company.id,
        first_name="Alex",
        last_name="Reed",
        full_name="Alex Reed",
    )
    test_db.add(other_contact)
    test_db.flush()
    other_email = EmailAddress(contact_id=other_contact.id, address="alex@vectorrobotics.example.com")
    test_db.add(other_email)
    test_db.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    test_db.add(
        EmailVerification(
            email_address_id=other_email.id,
            status="safe",
            verified_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    test_db.commit()

    with pytest.raises(OutreachEligibilityError, match="does not belong"):
        initialize_outreach_thread(test_db, opp.id, contact_1.id, other_email.id)


def test_thread_and_draft_reject_suppressed_contact(test_db):
    """7. Contact suppression blocks both thread initialization and subsequent draft generation."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db, contact_suppressed=1)

    with pytest.raises(OutreachEligibilityError, match="Contact .* is suppressed"):
        initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    # Also test suppression applied AFTER thread creation
    contact.suppressed = 0
    test_db.commit()
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    contact.suppressed = 1
    test_db.commit()

    provider = _StubProvider([_valid_json_payload()])
    with pytest.raises(OutreachEligibilityError, match="Contact .* is suppressed"):
        generate_and_persist_draft(test_db, thread.id, provider=provider)
    assert provider.prompts_seen == []
    assert test_db.query(Draft).count() == 0


def test_thread_and_draft_reject_suppressed_company(test_db):
    """8. Suppression on either opportunity company or contact company blocks initialization and drafting."""
    # Opportunity company suppressed
    _, _, opp, contact, email_obj = _seed_verified_prospect(
        test_db,
        opp_company_suppressed=1,
    )
    with pytest.raises(OutreachEligibilityError, match="organization .* is suppressed"):
        initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    # Contact belongs to a different suppressed company
    _, contact_company, opp2, contact2, email2 = _seed_verified_prospect(
        test_db,
        opp_company_suppressed=0,
        contact_company_suppressed=1,
        separate_contact_company=True,
        email_address="maya.partner@partner.example.com",
    )
    with pytest.raises(OutreachEligibilityError, match="Contact organization .* is suppressed"):
        initialize_outreach_thread(test_db, opp2.id, contact2.id, email2.id)

    # Post-thread company suppression blocks draft generation
    contact_company.suppressed = 0
    test_db.commit()
    thread = initialize_outreach_thread(test_db, opp2.id, contact2.id, email2.id)

    contact_company.suppressed = 1
    test_db.commit()
    provider = _StubProvider([_valid_json_payload()])
    with pytest.raises(OutreachEligibilityError, match="organization .* is suppressed"):
        generate_and_persist_draft(test_db, thread.id, provider=provider)
    assert test_db.query(Draft).count() == 0


def test_thread_and_draft_reject_suppressed_email_address(test_db):
    """9. Address suppression blocks both thread initialization and draft generation."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db, email_suppressed=1)

    with pytest.raises(OutreachEligibilityError, match="suppressed"):
        initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    email_obj.suppressed = 0
    test_db.commit()
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    email_obj.suppressed = 1
    test_db.commit()
    provider = _StubProvider([_valid_json_payload()])
    with pytest.raises(OutreachEligibilityError, match="suppressed"):
        generate_and_persist_draft(test_db, thread.id, provider=provider)


@pytest.mark.parametrize("usable_status", ["safe", "catch-all", "role_account"])
def test_approved_verification_statuses_are_usable(test_db, usable_status):
    """Confirmed Stage 3 policy: safe, catch-all, and role_account are usable when unexpired."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(
        test_db,
        verification_status=usable_status,
        email_address=f"{usable_status}@vectorrobotics.example.com",
    )
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)
    assert thread.status == "draft"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"verified": False},
        {"verified": True, "expired": True, "verification_status": "safe"},
        {"verified": True, "verification_status": "invalid"},
        {"verified": True, "verification_status": "unknown"},
        {"verified": True, "verification_status": "disposable"},
        {"verified": True, "verification_status": "spamtrap"},
        {"verified": True, "verification_status": "disabled"},
        {"verified": True, "verification_status": "inbox_full"},
    ],
)
def test_thread_and_draft_reject_unverified_expired_and_ineligible_statuses(test_db, kwargs):
    """10. Unverified, expired, or ineligible verification statuses are rejected."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db, **kwargs)
    with pytest.raises(OutreachEligibilityError, match="not eligible"):
        initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)


# ==============================================================================
# 11-22. Draft Persistence, Versioning & Retrieval Tests
# ==============================================================================


def test_generate_and_persist_initial_draft_success(test_db):
    """11, 13. Initial draft persists at version 1 with provider metadata, is_edited=0, and redacted prompt."""
    secret_note = "HIGHLY_SENSITIVE_CONTACT_NOTE_ABC"
    secret_email = "maya.secret@vectorrobotics.example.com"
    _, _, opp, contact, email_obj = _seed_verified_prospect(
        test_db,
        notes=secret_note,
        email_address=secret_email,
    )
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    custom_instruction = "Keep opening crisp and focus on observability."
    provider = _StubProvider([_valid_json_payload()], provider="gemini", model="gemini-3.5-flash-lite")

    draft = generate_and_persist_draft(
        test_db,
        thread.id,
        custom_instructions=custom_instruction,
        provider=provider,
    )

    assert draft.id is not None
    assert draft.outreach_thread_id == thread.id
    assert draft.version == 1
    assert draft.draft_type == "initial"
    assert draft.followup_number is None
    assert draft.subject == "Scaling telemetry reliability"
    assert draft.body == _valid_body()
    assert draft.llm_provider == "gemini"
    assert draft.llm_model == "gemini-3.5-flash-lite"
    assert draft.is_edited == 0

    # Prompt stored in DB must be redacted: no retrieved DB values, no custom instructions, no recipient email
    assert draft.generation_prompt is not None
    assert "<TRUSTED_SYSTEM_RULES>" in draft.generation_prompt
    assert "<UNTRUSTED_REFERENCE_DATA>" in draft.generation_prompt
    assert "[REDACTED]" in draft.generation_prompt
    assert "[REDACTED_CUSTOM_INSTRUCTIONS]" in draft.generation_prompt
    assert "Vector Robotics" not in draft.generation_prompt
    assert "Maya Lin" not in draft.generation_prompt
    assert secret_note not in draft.generation_prompt
    assert secret_email not in draft.generation_prompt
    assert custom_instruction not in draft.generation_prompt


def test_generate_and_persist_followup_draft_success(test_db):
    """12. Follow-up drafts persist with draft_type='followup', followup_number in 1..3, and is_edited=0."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)
    thread.status = "sent"
    test_db.commit()

    # Mocked Ollama provider verifying same persistence contract
    provider = _StubProvider([_valid_json_payload(subject="Following up on telemetry")], provider="ollama", model="llama3.2")
    draft = generate_and_persist_draft(
        test_db,
        thread.id,
        draft_type="followup",
        followup_number=1,
        provider=provider,
    )

    assert draft.draft_type == "followup"
    assert draft.followup_number == 1
    assert draft.version == 1
    assert draft.llm_provider == "ollama"
    assert draft.llm_model == "llama3.2"
    assert draft.is_edited == 0

    # Invalid draft_type / followup_number combinations rejected cleanly
    with pytest.raises(ValueError, match="Initial drafts must use followup_number=None"):
        generate_and_persist_draft(test_db, thread.id, draft_type="initial", followup_number=1, provider=provider)
    with pytest.raises(ValueError, match="followup_number to be 1, 2, or 3"):
        generate_and_persist_draft(test_db, thread.id, draft_type="followup", followup_number=4, provider=provider)
    with pytest.raises(OutreachEligibilityError, match="already been sent"):
        generate_and_persist_draft(test_db, thread.id, draft_type="initial", provider=provider)


def test_initial_draft_regeneration_creates_version_2_and_preserves_history(test_db):
    """14, 19. Regeneration creates version 2 while keeping version 1 immutable and unchanged."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    provider = _StubProvider(
        [
            _valid_json_payload(subject="Initial version one", marker="fleet telemetry v1"),
            _valid_json_payload(subject="Initial version two", marker="fleet telemetry v2"),
        ]
    )

    v1 = generate_and_persist_draft(test_db, thread.id, provider=provider)
    v1_snapshot = (
        v1.id,
        v1.version,
        v1.subject,
        v1.body,
        v1.created_at.replace(tzinfo=None),
    )

    v2 = generate_and_persist_draft(test_db, thread.id, provider=provider)

    assert v1.version == 1
    assert v2.version == 2
    assert v2.id != v1.id

    test_db.expire_all()
    reloaded_v1 = get_draft(test_db, v1_snapshot[0])
    assert reloaded_v1 is not None
    assert (
        reloaded_v1.id,
        reloaded_v1.version,
        reloaded_v1.subject,
        reloaded_v1.body,
        reloaded_v1.created_at.replace(tzinfo=None),
    ) == v1_snapshot


def test_independent_draft_type_and_followup_number_version_sequences(test_db):
    """15-16. Initial and follow-up numbers 1, 2, 3 maintain independent version counters."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    provider = _StubProvider(
        [
            _valid_json_payload(subject="Initial v1"),
            _valid_json_payload(subject="Initial v2"),
            _valid_json_payload(subject="Followup 1 v1"),
            _valid_json_payload(subject="Followup 1 v2"),
            _valid_json_payload(subject="Followup 2 v1"),
            _valid_json_payload(subject="Followup 3 v1"),
        ]
    )

    init_1 = generate_and_persist_draft(test_db, thread.id, draft_type="initial", provider=provider)
    init_2 = generate_and_persist_draft(test_db, thread.id, draft_type="initial", provider=provider)
    fu1_1 = generate_and_persist_draft(test_db, thread.id, draft_type="followup", followup_number=1, provider=provider)
    fu1_2 = generate_and_persist_draft(test_db, thread.id, draft_type="followup", followup_number=1, provider=provider)
    fu2_1 = generate_and_persist_draft(test_db, thread.id, draft_type="followup", followup_number=2, provider=provider)
    fu3_1 = generate_and_persist_draft(test_db, thread.id, draft_type="followup", followup_number=3, provider=provider)

    assert (init_1.version, init_2.version) == (1, 2)
    assert (fu1_1.version, fu1_2.version) == (1, 2)
    assert fu2_1.version == 1
    assert fu3_1.version == 1


def test_failed_generation_does_not_persist_or_consume_version(test_db):
    """17-18. Provider, parsing, and validation failures store no draft and do not skip version numbers."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    # First draft succeeds -> v1
    ok_provider = _StubProvider([_valid_json_payload(subject="Version one works")])
    v1 = generate_and_persist_draft(test_db, thread.id, provider=ok_provider)
    assert v1.version == 1

    # Failures: provider error, malformed JSON, placeholder rejection
    bad_provider = _StubProvider(
        [
            LLMGenerationError("Gemini timeout"),
            "not valid json at all",
            json.dumps({"subject": "Hello [COMPANY]", "body": _valid_body()}),
        ]
    )
    with pytest.raises(LLMGenerationError):
        generate_and_persist_draft(test_db, thread.id, provider=bad_provider)
    with pytest.raises(DraftValidationError):
        generate_and_persist_draft(test_db, thread.id, provider=bad_provider)
    with pytest.raises(DraftValidationError):
        generate_and_persist_draft(test_db, thread.id, provider=bad_provider)

    # Still only 1 draft persisted
    assert test_db.query(Draft).count() == 1

    # Next successful generation gets version 2 (not 5)
    retry_provider = _StubProvider([_valid_json_payload(subject="Version two succeeds")])
    v2 = generate_and_persist_draft(test_db, thread.id, provider=retry_provider)
    assert v2.version == 2


def test_draft_retrieval_operations_and_ordering(test_db):
    """20-22. Specific draft, all versions (isolated by type), latest version, and thread retrieval work."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    provider = _StubProvider(
        [
            _valid_json_payload(subject="Init 1"),
            _valid_json_payload(subject="Init 2"),
            _valid_json_payload(subject="FU1 v1"),
            _valid_json_payload(subject="FU2 v1"),
            _valid_json_payload(subject="FU1 v2"),
        ]
    )
    init1 = generate_and_persist_draft(test_db, thread.id, "initial", provider=provider)
    init2 = generate_and_persist_draft(test_db, thread.id, "initial", provider=provider)
    fu1_v1 = generate_and_persist_draft(test_db, thread.id, "followup", 1, provider=provider)
    fu2_v1 = generate_and_persist_draft(test_db, thread.id, "followup", 2, provider=provider)
    fu1_v2 = generate_and_persist_draft(test_db, thread.id, "followup", 1, provider=provider)

    fetched_thread = get_outreach_thread(test_db, thread.id)
    assert fetched_thread is not None
    assert fetched_thread.id == thread.id
    assert get_outreach_thread(test_db, 999999) is None

    assert get_draft(test_db, init1.id).subject == "Init 1"
    assert get_draft(test_db, 999999) is None

    initials = list_draft_versions(test_db, thread.id, "initial")
    assert [d.id for d in initials] == [init1.id, init2.id]
    assert all(d.draft_type == "initial" and d.followup_number is None for d in initials)

    fu1_all = list_draft_versions(test_db, thread.id, "followup", followup_number=1)
    assert [d.id for d in fu1_all] == [fu1_v1.id, fu1_v2.id]

    fu_all = list_draft_versions(test_db, thread.id, "followup")
    assert [d.id for d in fu_all] == [fu1_v1.id, fu1_v2.id, fu2_v1.id]

    latest_init = get_latest_draft(test_db, thread.id, "initial")
    assert latest_init is not None and latest_init.id == init2.id

    latest_fu1 = get_latest_draft(test_db, thread.id, "followup", followup_number=1)
    assert latest_fu1 is not None and latest_fu1.id == fu1_v2.id

    latest_fu3 = get_latest_draft(test_db, thread.id, "followup", followup_number=3)
    assert latest_fu3 is None


# ==============================================================================
# 23-27. Concurrency, Audit Redaction, Rollback & Partial Unique Index Tests
# ==============================================================================


def test_concurrent_version_allocation_and_thread_init():
    """23. Concurrent requests allocate sequential unique versions and handle concurrent thread init safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "concurrent_drafts.db")
        file_engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(file_engine, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA busy_timeout=5000;")
            ensure_audit_log_triggers(cur)
            cur.close()

        Base.metadata.create_all(file_engine)
        SessionMaker = sessionmaker(autocommit=False, autoflush=False, bind=file_engine)

        try:
            seed = SessionMaker()
            _, _, opp, contact, email_obj = _seed_verified_prospect(seed)
            opp_id, contact_id, email_id = opp.id, contact.id, email_obj.id
            seed.close()

            # Concurrent thread initialization with same email
            init_barrier = threading.Barrier(3, timeout=5.0)

            def init_worker(_idx: int) -> int:
                s = SessionMaker()
                try:
                    init_barrier.wait()
                    th = initialize_outreach_thread(s, opp_id, contact_id, email_id)
                    return th.id
                finally:
                    s.close()

            with ThreadPoolExecutor(max_workers=3) as pool:
                thread_ids = list(pool.map(init_worker, range(3)))

            assert len(set(thread_ids)) == 1
            thread_id = thread_ids[0]

            # Concurrent draft version allocation on the same thread
            draft_barrier = threading.Barrier(4, timeout=5.0)

            def draft_worker(idx: int) -> int:
                s = SessionMaker()
                try:
                    provider = _StubProvider(
                        [_valid_json_payload(subject=f"Concurrent draft #{idx}")]
                    )
                    draft_barrier.wait()
                    d = generate_and_persist_draft(s, thread_id, provider=provider)
                    return d.version
                finally:
                    s.close()

            with ThreadPoolExecutor(max_workers=4) as pool:
                versions = list(pool.map(draft_worker, range(4)))

            assert sorted(versions) == [1, 2, 3, 4]
            assert get_draft_lock_registry().active_lock_count() == 0

            check = SessionMaker()
            stored = list_draft_versions(check, thread_id, "initial")
            assert [d.version for d in stored] == [1, 2, 3, 4]
            check.close()
        finally:
            file_engine.dispose()


def test_audit_logging_and_sensitive_data_redaction(test_db, caplog):
    """24. Audit logs and application logs never expose keys, credentials, emails, notes, full prompts, or bodies."""
    secret_note = "PRIVATE_NOTE_DO_NOT_AUDIT_9981"
    secret_email = "maya.audit.secret@vectorrobotics.example.com"
    secret_key = "AIzaSy_SECRET_KEY_AUDIT_TEST"
    custom_pref = "CUSTOM_PREF_DO_NOT_STORE_RAW"

    _, _, opp, contact, email_obj = _seed_verified_prospect(
        test_db,
        notes=secret_note,
        email_address=secret_email,
    )

    with caplog.at_level(logging.DEBUG, logger="app.services.draft_service"):
        thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

        # Successful generation audit
        ok_provider = _StubProvider([_valid_json_payload(marker="UNIQUE_BODY_MARKER_7744")])
        draft = generate_and_persist_draft(
            test_db,
            thread.id,
            custom_instructions=custom_pref,
            provider=ok_provider,
        )

        # Failed generation audit (error message includes simulated secret key to verify sanitization)
        failing_provider = _StubProvider([LLMGenerationError(f"Error with {secret_key} and {secret_email}")])
        with pytest.raises(LLMGenerationError):
            generate_and_persist_draft(test_db, thread.id, provider=failing_provider)

    audit_entries = test_db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
    event_types = [entry.event_type for entry in audit_entries]
    assert "outreach_thread_created" in event_types
    assert "draft_generated" in event_types
    assert "draft_generation_failed" in event_types

    success_audit = next(e for e in audit_entries if e.event_type == "draft_generated")
    meta = json.loads(success_audit.metadata_json or "{}")
    assert meta["thread_id"] == thread.id
    assert meta["draft_id"] == draft.id
    assert meta["version"] == 1
    assert meta["draft_type"] == "initial"
    assert meta["provider"] == "gemini"
    assert meta["model"] == "gemini-3.5-flash-lite"

    # Verify zero sensitive data across all audit log descriptions/metadata and app logs
    all_audit_text = "\n".join(f"{e.description}\n{e.metadata_json or ''}" for e in audit_entries)
    for sensitive in (
        secret_note,
        secret_email,
        secret_key,
        custom_pref,
        "UNIQUE_BODY_MARKER_7744",
        "<TRUSTED_SYSTEM_RULES>",
    ):
        assert sensitive not in all_audit_text
        assert sensitive not in caplog.text


def test_transaction_rollback_behavior(test_db):
    """25. Persistence failures roll back cleanly without leaving partial drafts, and caller-managed txs work."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    # Case A: Persistence failure after Draft flush rolls back completely
    provider = _StubProvider([_valid_json_payload(subject="Should roll back")])
    with patch("app.services.draft_service.write_audit_log", side_effect=RuntimeError("Simulated audit DB crash")):
        with pytest.raises(RuntimeError, match="Simulated audit DB crash"):
            generate_and_persist_draft(test_db, thread.id, provider=provider)

    assert test_db.query(Draft).count() == 0

    # Subsequent successful draft allocates version 1 (no leaked version)
    v1 = generate_and_persist_draft(
        test_db,
        thread.id,
        provider=_StubProvider([_valid_json_payload(subject="Recovered v1")]),
    )
    assert v1.version == 1

    # Case B: Caller already has an active explicit transaction (must NOT execute BEGIN IMMEDIATE or commit)
    if test_db.in_transaction():
        test_db.rollback()

    executed_sql: list[str] = []

    def _capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        executed_sql.append(statement.strip().upper())

    engine = test_db.get_bind()
    event.listen(engine, "before_cursor_execute", _capture_sql)
    try:
        test_db.begin()
        assert test_db.in_transaction() is True

        v2 = generate_and_persist_draft(
            test_db,
            thread.id,
            provider=_StubProvider([_valid_json_payload(subject="Inside caller tx")]),
        )
        assert v2.version == 2
        assert test_db.in_transaction() is True
        assert not any("BEGIN IMMEDIATE" in sql for sql in executed_sql)
        test_db.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", _capture_sql)

    # Rolling back caller's transaction removes uncommitted v2 while keeping committed v1
    assert [d.version for d in list_draft_versions(test_db, thread.id, "initial")] == [1]

    # Case C: Caller has uncommitted flushed DML inside an autobegun transaction
    executed_sql.clear()
    event.listen(engine, "before_cursor_execute", _capture_sql)
    try:
        test_db.add(
            Company(
                name="Uncommitted Tx Co",
                type="employer",
            )
        )
        test_db.flush()
        v2_b = generate_and_persist_draft(
            test_db,
            thread.id,
            provider=_StubProvider([_valid_json_payload(subject="Inside flushed caller tx")]),
        )
        assert v2_b.version == 2
        assert not any("BEGIN IMMEDIATE" in sql for sql in executed_sql)
        test_db.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", _capture_sql)
    assert [d.version for d in list_draft_versions(test_db, thread.id, "initial")] == [1]


@pytest.mark.parametrize("blocked_status", ["suppressed", "replied", "bounced", "closed", "sending"])
def test_ineligible_thread_statuses_blocked_from_drafting(test_db, blocked_status):
    """Threads in suppressed, replied, bounced, closed, or sending status cannot generate drafts."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)
    thread.status = blocked_status
    test_db.commit()

    provider = _StubProvider([_valid_json_payload(), _valid_json_payload()])
    with pytest.raises(OutreachEligibilityError, match="not eligible for drafting"):
        generate_and_persist_draft(test_db, thread.id, draft_type="initial", provider=provider)
    with pytest.raises(OutreachEligibilityError, match="not eligible for drafting"):
        generate_and_persist_draft(
            test_db, thread.id, draft_type="followup", followup_number=1, provider=provider
        )
    assert provider.prompts_seen == []
    assert test_db.query(Draft).count() == 0


def test_partial_unique_index_enforces_initial_draft_uniqueness(test_db):
    """26. SQLite partial unique index rejects duplicate initial draft versions even when followup_number IS NULL."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    d1 = Draft(
        outreach_thread_id=thread.id,
        version=1,
        draft_type="initial",
        followup_number=None,
        subject="Initial draft v1",
        body=_valid_body(),
        is_edited=0,
    )
    test_db.add(d1)
    test_db.commit()

    # Duplicate (thread_id, 'initial', NULL, 1) must raise IntegrityError via uq_drafts_initial_version
    dup_initial = Draft(
        outreach_thread_id=thread.id,
        version=1,
        draft_type="initial",
        followup_number=None,
        subject="Duplicate initial v1",
        body=_valid_body(),
        is_edited=0,
    )
    test_db.add(dup_initial)
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()

    # Follow-up drafts with version=1 (different followup_number) remain allowed
    fu1 = Draft(
        outreach_thread_id=thread.id,
        version=1,
        draft_type="followup",
        followup_number=1,
        subject="Followup 1 v1",
        body=_valid_body(),
        is_edited=0,
    )
    test_db.add(fu1)
    test_db.commit()

    # Duplicate follow-up version blocked by existing uq_drafts_thread_version
    dup_fu1 = Draft(
        outreach_thread_id=thread.id,
        version=1,
        draft_type="followup",
        followup_number=1,
        subject="Duplicate followup 1 v1",
        body=_valid_body(),
        is_edited=0,
    )
    test_db.add(dup_fu1)
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_alembic_migration_upgrade_downgrade_roundtrip(monkeypatch):
    """27. Alembic migration cleanly creates and removes uq_drafts_initial_version on upgrade/downgrade."""
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    alembic_dir = os.path.join(backend_dir, "alembic")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "migration_test.db")
        monkeypatch.setenv("DATABASE_PATH", db_file)
        get_settings.cache_clear()

        cfg = Config(alembic_ini)
        cfg.set_main_option("script_location", alembic_dir)
        cfg.set_main_option("path_separator", "os")
        # Prevent alembic's fileConfig() from disabling existing app loggers during pytest runs
        cfg.config_file_name = None

        orig_cwd = os.getcwd()
        try:
            os.chdir(backend_dir)
            command.upgrade(cfg, "head")

            conn = sqlite3.connect(db_file)
            idx_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                ("uq_drafts_initial_version",),
            ).fetchone()
            conn.close()
            assert idx_row is not None
            assert "WHERE draft_type = 'initial' AND followup_number IS NULL" in idx_row[0]

            command.downgrade(cfg, "4a386b6fd0d9")

            conn = sqlite3.connect(db_file)
            idx_after_downgrade = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                ("uq_drafts_initial_version",),
            ).fetchone()
            conn.close()
            assert idx_after_downgrade is None

            command.upgrade(cfg, "head")

            conn = sqlite3.connect(db_file)
            idx_after_reupgrade = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                ("uq_drafts_initial_version",),
            ).fetchone()
            conn.close()
            assert idx_after_reupgrade is not None
        finally:
            os.chdir(orig_cwd)
            get_settings.cache_clear()


def test_provider_missing_credentials_does_not_persist_draft(test_db):
    """Unconfigured provider credentials raise MissingCredentialError without creating a draft."""
    _, _, opp, contact, email_obj = _seed_verified_prospect(test_db)
    thread = initialize_outreach_thread(test_db, opp.id, contact.id, email_obj.id)

    mock_settings = MagicMock(spec=Settings)
    mock_settings.llm_provider = "gemini"
    mock_settings.validate_gemini_credentials.side_effect = MissingCredentialError("GEMINI_API_KEY missing")

    with (
        patch("app.providers.llm_factory.get_settings", return_value=mock_settings),
        patch("app.integrations.gemini.get_settings", return_value=mock_settings),
    ):
        with pytest.raises(MissingCredentialError, match="GEMINI_API_KEY missing"):
            generate_and_persist_draft(test_db, thread.id, provider_name="gemini")

    assert test_db.query(Draft).count() == 0
