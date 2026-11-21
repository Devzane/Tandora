"""Organization & Opportunity Management Service."""

from datetime import datetime, timezone
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from app.models.company import Company
from app.models.opportunity import Opportunity
from app.models.contact import Contact
from app.models.opportunity_contact import OpportunityContact
from app.models.outreach_thread import OutreachThread
from app.models.followup_schedule import FollowupSchedule
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.schemas.opportunity import OpportunityCreate, OpportunityUpdate
from app.services.audit_service import write_audit_log


def create_company(db: Session, data: CompanyCreate) -> Company:
    """Create a new company record and record audit log."""
    company = Company(
        name=data.name.strip(),
        website=data.website.strip() if data.website else None,
        industry=data.industry.strip() if data.industry else None,
        description=data.description,
        type=data.type,
        source_url=data.source_url,
    )
    db.add(company)
    db.flush()
    write_audit_log(
        db,
        event_type="company_created",
        description=f"Created company '{company.name}' (type={company.type})",
        entity_type="company",
        entity_id=company.id,
    )
    return company


def get_company(db: Session, company_id: int) -> Company | None:
    """Fetch company by ID."""
    return db.get(Company, company_id)


def list_companies(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    type: str | None = None,
    suppressed: int | None = None,
) -> tuple[list[Company], int]:
    """List companies with optional filtering and pagination."""
    query = select(Company)
    if type:
        query = query.where(Company.type == type)
    if suppressed is not None:
        query = query.where(Company.suppressed == suppressed)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.execute(query.order_by(Company.name.asc()).offset(skip).limit(limit)).scalars().all()
    return list(items), total


def update_company(db: Session, company_id: int, data: CompanyUpdate) -> Company | None:
    """Update company details."""
    company = get_company(db, company_id)
    if not company:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        setattr(company, field, val)

    company.updated_at = datetime.now(timezone.utc)
    db.flush()
    write_audit_log(
        db,
        event_type="company_updated",
        description=f"Updated company '{company.name}'",
        entity_type="company",
        entity_id=company.id,
    )
    return company


def set_company_suppression(
    db: Session, company_id: int, suppressed: bool, reason: str | None = None
) -> Company | None:
    """Toggle company suppression and cascade-cancel pending follow-ups for employed contacts."""
    company = get_company(db, company_id)
    if not company:
        return None

    now = datetime.now(timezone.utc)
    if suppressed:
        company.suppressed = 1
        company.suppressed_reason = reason or "Manual suppression"
        company.suppressed_at = now

        # Multi-level suppression: Cancel pending followups for all contacts at this company
        subquery_threads = (
            select(OutreachThread.id)
            .join(Contact, Contact.id == OutreachThread.contact_id)
            .where(Contact.company_id == company_id)
        )
        db.execute(
            update(FollowupSchedule)
            .where(
                FollowupSchedule.outreach_thread_id.in_(subquery_threads),
                FollowupSchedule.status == "pending",
            )
            .values(
                status="cancelled",
                suppressed_reason=f"Company suppressed: {reason or 'Manual suppression'}",
                suppressed_at=now,
                updated_at=now,
            )
        )
        write_audit_log(
            db,
            event_type="suppression_added",
            description=f"Suppressed company '{company.name}': {company.suppressed_reason}",
            entity_type="company",
            entity_id=company.id,
        )
    else:
        company.suppressed = 0
        company.suppressed_reason = None
        company.suppressed_at = None
        write_audit_log(
            db,
            event_type="suppression_removed",
            description=f"Un-suppressed company '{company.name}'",
            entity_type="company",
            entity_id=company.id,
        )

    company.updated_at = now
    db.flush()
    return company


# --- Opportunity Operations ---

def create_opportunity(db: Session, data: OpportunityCreate) -> Opportunity:
    """Create a new opportunity record."""
    opportunity = Opportunity(
        company_id=data.company_id,
        type=data.type,
        title=data.title.strip(),
        description=data.description,
        source_url=data.source_url,
        status=data.status,
    )
    db.add(opportunity)
    db.flush()
    write_audit_log(
        db,
        event_type="opportunity_created",
        description=f"Created opportunity '{opportunity.title}' for company ID {opportunity.company_id}",
        entity_type="opportunity",
        entity_id=opportunity.id,
    )
    return opportunity


def get_opportunity(db: Session, opportunity_id: int) -> Opportunity | None:
    """Fetch opportunity by ID."""
    return db.get(Opportunity, opportunity_id)


def list_opportunities(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    company_id: int | None = None,
    status: str | None = None,
) -> tuple[list[Opportunity], int]:
    """List opportunities with filtering and pagination."""
    query = select(Opportunity)
    if company_id:
        query = query.where(Opportunity.company_id == company_id)
    if status:
        query = query.where(Opportunity.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.execute(query.order_by(Opportunity.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    return list(items), total


def update_opportunity(db: Session, opportunity_id: int, data: OpportunityUpdate) -> Opportunity | None:
    """Update opportunity details."""
    opportunity = get_opportunity(db, opportunity_id)
    if not opportunity:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        setattr(opportunity, field, val)

    opportunity.updated_at = datetime.now(timezone.utc)
    db.flush()
    write_audit_log(
        db,
        event_type="opportunity_updated",
        description=f"Updated opportunity '{opportunity.title}'",
        entity_type="opportunity",
        entity_id=opportunity.id,
    )
    return opportunity


# --- Opportunity - Contact Association Operations ---

def link_contact_to_opportunity(db: Session, opportunity_id: int, contact_id: int) -> OpportunityContact:
    """Link a contact to an opportunity via the opportunity_contacts join table."""
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise ValueError(f"Opportunity with ID {opportunity_id} not found")
    contact = db.get(Contact, contact_id)
    if not contact:
        raise ValueError(f"Contact with ID {contact_id} not found")

    existing = db.scalar(
        select(OpportunityContact).where(
            OpportunityContact.opportunity_id == opportunity_id,
            OpportunityContact.contact_id == contact_id,
        )
    )
    if existing:
        return existing

    link = OpportunityContact(opportunity_id=opportunity_id, contact_id=contact_id)
    db.add(link)
    db.flush()
    write_audit_log(
        db,
        event_type="opportunity_contact_linked",
        description=f"Linked contact ID {contact_id} to opportunity ID {opportunity_id}",
        entity_type="opportunity",
        entity_id=opportunity_id,
    )
    return link


def unlink_contact_from_opportunity(db: Session, opportunity_id: int, contact_id: int) -> bool:
    """Unlink a contact from an opportunity."""
    link = db.scalar(
        select(OpportunityContact).where(
            OpportunityContact.opportunity_id == opportunity_id,
            OpportunityContact.contact_id == contact_id,
        )
    )
    if not link:
        return False
    db.delete(link)
    db.flush()
    write_audit_log(
        db,
        event_type="opportunity_contact_unlinked",
        description=f"Unlinked contact ID {contact_id} from opportunity ID {opportunity_id}",
        entity_type="opportunity",
        entity_id=opportunity_id,
    )
    return True


def get_opportunity_contacts(db: Session, opportunity_id: int) -> list[Contact]:
    """Retrieve all contacts linked to a specific opportunity."""
    query = (
        select(Contact)
        .join(OpportunityContact, OpportunityContact.contact_id == Contact.id)
        .where(OpportunityContact.opportunity_id == opportunity_id)
        .order_by(Contact.full_name.asc())
    )
    return list(db.execute(query).scalars().all())


def get_contact_opportunities(db: Session, contact_id: int) -> list[Opportunity]:
    """Retrieve all opportunities linked to a specific contact."""
    query = (
        select(Opportunity)
        .join(OpportunityContact, OpportunityContact.opportunity_id == Opportunity.id)
        .where(OpportunityContact.contact_id == contact_id)
        .order_by(Opportunity.created_at.desc())
    )
    return list(db.execute(query).scalars().all())

