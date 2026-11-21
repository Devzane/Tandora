"""Capture Ingestion Service."""

import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.capture import Capture
from app.models.company import Company
from app.models.opportunity_contact import OpportunityContact
from app.schemas.capture import CapturePayload, CaptureResponse
from app.schemas.company import CompanyCreate
from app.schemas.opportunity import OpportunityCreate
from app.schemas.contact import ContactCreate
from app.services.organization_service import create_company, create_opportunity
from app.services.contact_service import create_contact
from app.services.audit_service import write_audit_log


def ingest_capture(db: Session, payload: CapturePayload) -> CaptureResponse:
    """Ingest prospect, organization, and opportunity data from web or extension capture."""
    company_id: int | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
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

    # 4. Record Raw Capture Entry
    raw_json = json.dumps(payload.raw_payload) if payload.raw_payload else "{}"
    page_type = "profile" if payload.contact else ("job_posting" if payload.opportunity else "company")
    capture = Capture(
        capture_type=payload.source_type,
        page_type=page_type,
        source_url=payload.source_url or "http://localhost",
        raw_payload=raw_json,
        company_id=company_id,
        contact_id=contact_id,
        opportunity_id=opportunity_id,
        captured_at=datetime.now(timezone.utc),
    )
    db.add(capture)
    db.flush()

    # 5. Audit Log
    write_audit_log(
        db,
        event_type="prospect_captured",
        description=f"Ingested capture #{capture.id} via '{payload.source_type}' (Contact ID: {contact_id}, Company ID: {company_id})",
        entity_type="capture",
        entity_id=capture.id,
        metadata={"source_type": payload.source_type, "duplicate_flag": duplicate_flag},
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
        duplicate_flag=duplicate_flag,
        message=msg,
    )
