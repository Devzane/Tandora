"""Capture Ingestion Service."""

import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.capture import Capture
from app.models.company import Company
from app.models.opportunity_contact import OpportunityContact
from app.models.linkedin_post import LinkedInPost
from app.schemas.capture import CapturePayload, CaptureResponse
from app.schemas.company import CompanyCreate
from app.schemas.opportunity import OpportunityCreate
from app.schemas.contact import ContactCreate
from app.services.organization_service import create_company, create_opportunity
from app.services.contact_service import create_contact
from app.services.audit_service import write_audit_log


def ingest_capture(db: Session, payload: CapturePayload) -> CaptureResponse:
    """Ingest prospect, organization, opportunity, and LinkedIn post data from web or extension capture."""
    company_id: int | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    post_id: int | None = None
    duplicate_flag: int = 0

    # 1. Process Company
    if payload.company:
        stmt = select(Company).where(Company.name.ilike(payload.company.name.strip()))
        existing_company = db.execute(stmt).scalars().first()
        if existing_company:
            company_id = existing_company.id
        else:
            comp_create = CompanyCreate(
                name=payload.company.name,
                website=payload.company.website,
                industry=payload.company.industry,
                description=payload.company.description,
                type=payload.company.type,
                source_url=payload.company.source_url or payload.source_url,
            )
            created_comp = create_company(db, comp_create)
            company_id = created_comp.id
    elif payload.post and payload.post.company_mentioned:
        comp_name = payload.post.company_mentioned.strip()
        stmt = select(Company).where(Company.name.ilike(comp_name))
        existing_company = db.execute(stmt).scalars().first()
        if existing_company:
            company_id = existing_company.id
        else:
            comp_create = CompanyCreate(
                name=comp_name,
                type="employer",
                source_url=payload.post.post_url or payload.source_url,
            )
            created_comp = create_company(db, comp_create)
            company_id = created_comp.id

    # 2. Process Opportunity
    if payload.opportunity and company_id:
        opp_create = OpportunityCreate(
            company_id=company_id,
            title=payload.opportunity.title,
            description=payload.opportunity.description,
            type=payload.opportunity.type,
            source_url=payload.opportunity.source_url or payload.source_url,
            status="active",
        )
        created_opp = create_opportunity(db, opp_create)
        opportunity_id = created_opp.id

    # 3. Process Contact
    if payload.contact:
        contact_create = ContactCreate(
            company_id=company_id,
            first_name=payload.contact.first_name,
            last_name=payload.contact.last_name,
            headline=payload.contact.headline,
            linkedin_url=payload.contact.linkedin_url,
            notes=payload.contact.notes,
            roles=payload.contact.roles,
            emails=payload.contact.emails,
            phones=payload.contact.phones,
        )
        contact, was_merged = create_contact(db, contact_create)
        contact_id = contact.id
        duplicate_flag = contact.duplicate_flag

        # Link contact to opportunity if both present
        if opportunity_id:
            stmt_link = select(OpportunityContact).where(
                OpportunityContact.opportunity_id == opportunity_id,
                OpportunityContact.contact_id == contact_id,
            )
            if not db.execute(stmt_link).scalars().first():
                link = OpportunityContact(
                    opportunity_id=opportunity_id,
                    contact_id=contact_id,
                )
                db.add(link)
                db.flush()

    # 4. Process LinkedIn Post Author (if present and configured)
    author_contact_id: int | None = None
    if payload.post and payload.post.create_author_contact and payload.post.author_name:
        parts = payload.post.author_name.strip().split(" ", 1)
        author_first = parts[0]
        author_last = parts[1] if len(parts) > 1 else None
        author_create = ContactCreate(
            company_id=company_id,
            first_name=author_first,
            last_name=author_last,
            headline=payload.post.author_headline,
            linkedin_url=payload.post.author_linkedin_url,
            notes=f"Author of captured post: {payload.post.post_url}",
        )
        author_contact, _ = create_contact(db, author_create)
        author_contact_id = author_contact.id

        if not contact_id:
            contact_id = author_contact_id
            duplicate_flag = author_contact.duplicate_flag

        if opportunity_id:
            stmt_link = select(OpportunityContact).where(
                OpportunityContact.opportunity_id == opportunity_id,
                OpportunityContact.contact_id == author_contact_id,
            )
            if not db.execute(stmt_link).scalars().first():
                link = OpportunityContact(
                    opportunity_id=opportunity_id,
                    contact_id=author_contact_id,
                )
                db.add(link)
                db.flush()

    # 5. Record Raw Capture Entry
    capture_type = payload.capture_type or payload.source_type or "generic_web"
    page_type = payload.page_type or (
        "linkedin_post"
        if payload.post
        else (
            "linkedin_profile"
            if payload.contact
            else ("linkedin_company" if payload.company and not payload.opportunity else "job_listing")
        )
    )
    raw_json = json.dumps(payload.raw_payload) if payload.raw_payload else "{}"
    captured_at = payload.captured_at or datetime.now(timezone.utc)

    capture = Capture(
        capture_type=capture_type,
        page_type=page_type,
        source_url=payload.source_url or (payload.post.post_url if payload.post else "http://localhost"),
        source_title=payload.source_title,
        selected_text=payload.selected_text,
        user_notes=payload.user_notes,
        raw_payload=raw_json,
        company_id=company_id,
        contact_id=contact_id,
        opportunity_id=opportunity_id,
        captured_at=captured_at,
    )
    db.add(capture)
    db.flush()

    # 6. Create LinkedIn Post Record (if present)
    if payload.post:
        post_record = LinkedInPost(
            capture_id=capture.id,
            author_name=payload.post.author_name.strip(),
            author_linkedin_url=payload.post.author_linkedin_url.strip() if payload.post.author_linkedin_url else None,
            author_headline=payload.post.author_headline.strip() if payload.post.author_headline else None,
            post_url=payload.post.post_url.strip(),
            post_text=payload.post.post_text.strip(),
            post_timestamp=payload.post.post_timestamp,
            company_mentioned=payload.post.company_mentioned,
            author_contact_id=author_contact_id,
            opportunity_id=opportunity_id,
        )
        db.add(post_record)
        db.flush()
        post_id = post_record.id

    # 7. Audit Log
    write_audit_log(
        db,
        event_type="prospect_captured",
        description=f"Ingested capture #{capture.id} ({capture_type}/{page_type}) (Contact ID: {contact_id}, Company ID: {company_id}, Opportunity ID: {opportunity_id}, Post ID: {post_id})",
        entity_type="capture",
        entity_id=capture.id,
        metadata={"capture_type": capture_type, "duplicate_flag": duplicate_flag, "post_id": post_id},
    )

    db.commit()

    msg = "Capture ingested successfully."
    if duplicate_flag:
        msg += " Warning: Contact flagged as potential duplicate for review."

    return CaptureResponse(
        capture_id=capture.id,
        company_id=company_id,
        opportunity_id=opportunity_id,
        contact_id=contact_id,
        post_id=post_id,
        duplicate_flag=duplicate_flag,
        message=msg,
    )
