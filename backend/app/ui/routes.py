"""Server-Rendered Local Web UI Routes."""

import logging
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.config import get_settings
from app.models.company import Company
from app.models.opportunity import Opportunity
from app.models.contact import Contact
from app.models.email_address import EmailAddress
from app.models.phone_number import PhoneNumber
from app.models.audit_log import AuditLog
from app.models.send_attempt import SendAttempt
from app.models.app_config import AppConfig

from app.schemas.company import CompanyCreate
from app.schemas.opportunity import OpportunityCreate
from app.schemas.contact import (
    ContactCreate,
    EmailAddressCreate,
    PhoneNumberCreate,
)
from app.services.organization_service import (
    create_company,
    get_company,
    list_companies,
    set_company_suppression,
    create_opportunity,
    get_opportunity,
    list_opportunities,
)
from app.services.contact_service import (
    create_contact,
    get_contact,
    list_contacts,
    set_contact_suppression,
    add_email_address,
    set_email_suppression,
    add_phone_number,
)
from app.services.verification_service import (
    verify_email_address,
    approve_catch_all,
    get_verification_stats,
)

logger = logging.getLogger(__name__)

templates_path = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

router = APIRouter(include_in_schema=False)


# --- Dashboard ---

@router.get("/", response_class=HTMLResponse)
def dashboard_view(request: Request, db: Session = Depends(get_db)):
    """Render dashboard overview."""
    settings = get_settings()

    total_contacts = db.scalar(select(func.count()).select_from(Contact)) or 0
    total_companies = db.scalar(select(func.count()).select_from(Company)) or 0
    total_opportunities = db.scalar(
        select(func.count()).select_from(Opportunity).where(Opportunity.status == "active")
    ) or 0

    # Count candidate duplicates
    duplicate_count = db.scalar(
        select(func.count()).select_from(Contact).where(Contact.duplicate_flag == 1)
    ) or 0

    # Sends today count
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_sends = db.scalar(
        select(func.count())
        .select_from(SendAttempt)
        .where(
            SendAttempt.status.in_(["sent", "sending"]),
            SendAttempt.created_at >= today_start,
        )
    ) or 0

    # Sending paused state
    config_paused = db.get(AppConfig, "sending_paused")
    sending_paused = config_paused.value.lower() == "true" if config_paused else False

    # Verification statistics
    verification_stats = get_verification_stats(db)

    # Recent audit logs
    audit_logs = db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8)
    ).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_tab": "dashboard",
            "total_contacts": total_contacts,
            "total_companies": total_companies,
            "total_opportunities": total_opportunities,
            "duplicate_count": duplicate_count,
            "daily_sends_today": daily_sends,
            "daily_limit": settings.daily_sending_limit,
            "sending_paused": sending_paused,
            "dry_run": settings.dry_run,
            "unapproved_catchalls": 0,
            "suppressed_by_verification": verification_stats["suppressed_by_verification"],
            "approved_active_count": verification_stats["approved_active_count"],
            "total_credits_used": verification_stats["total_credits_used"],
            "audit_logs": audit_logs,
        },
    )


# --- Organizations ---

@router.get("/organizations", response_class=HTMLResponse)
def organizations_list_view(
    request: Request,
    type: str | None = None,
    suppressed: int | None = None,
    db: Session = Depends(get_db),
):
    """List organizations."""
    companies, _ = list_companies(db, skip=0, limit=100, type=type, suppressed=suppressed)
    return templates.TemplateResponse(
        request=request,
        name="organizations.html",
        context={
            "active_tab": "organizations",
            "companies": companies,
            "current_type": type,
            "current_suppressed": suppressed,
        },
    )


@router.get("/organizations/new", response_class=HTMLResponse)
def organization_new_view(request: Request):
    """Form to create a new organization."""
    return templates.TemplateResponse(
        request=request,
        name="organization_new.html",
        context={"active_tab": "organizations"},
    )


@router.post("/organizations/new")
def organization_create_action(
    name: str = Form(...),
    type: str = Form("employer"),
    industry: str | None = Form(None),
    website: str | None = Form(None),
    source_url: str | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Handle new organization submission."""
    data = CompanyCreate(
        name=name,
        type=type,
        industry=industry or None,
        website=website or None,
        source_url=source_url or None,
        description=description or None,
    )
    comp = create_company(db, data)
    db.commit()
    return RedirectResponse(url=f"/organizations/{comp.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/organizations/{company_id}", response_class=HTMLResponse)
def organization_detail_view(company_id: int, request: Request, db: Session = Depends(get_db)):
    """Display company details, opportunities, and employed contacts."""
    company = get_company(db, company_id)
    if not company:
        return RedirectResponse(url="/organizations", status_code=status.HTTP_303_SEE_OTHER)

    opportunities, _ = list_opportunities(db, company_id=company_id, limit=50)
    contacts, _ = list_contacts(db, company_id=company_id, limit=50)

    return templates.TemplateResponse(
        request=request,
        name="organization_detail.html",
        context={
            "active_tab": "organizations",
            "company": company,
            "opportunities": opportunities,
            "contacts": contacts,
        },
    )


@router.post("/organizations/{company_id}/suppress")
def organization_suppress_action(
    company_id: int,
    suppressed: int = Form(...),
    reason: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Toggle organization suppression."""
    set_company_suppression(db, company_id, bool(suppressed), reason)
    db.commit()
    return RedirectResponse(url=f"/organizations/{company_id}", status_code=status.HTTP_303_SEE_OTHER)


# --- Opportunities ---

@router.get("/opportunities", response_class=HTMLResponse)
def opportunities_list_view(request: Request, db: Session = Depends(get_db)):
    """List opportunities."""
    opportunities, _ = list_opportunities(db, skip=0, limit=100)
    return templates.TemplateResponse(
        request=request,
        name="opportunities.html",
        context={
            "active_tab": "opportunities",
            "opportunities": opportunities,
        },
    )


@router.get("/opportunities/new", response_class=HTMLResponse)
def opportunity_new_view(
    request: Request,
    company_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Form to create an opportunity."""
    companies, _ = list_companies(db, skip=0, limit=200)
    return templates.TemplateResponse(
        request=request,
        name="opportunity_new.html",
        context={
            "active_tab": "opportunities",
            "companies": companies,
            "selected_company_id": company_id,
        },
    )


@router.post("/opportunities/new")
def opportunity_create_action(
    company_id: int = Form(...),
    title: str = Form(...),
    type: str = Form("employment"),
    status_val: str = Form("active", alias="status"),
    source_url: str | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Handle new opportunity submission."""
    data = OpportunityCreate(
        company_id=company_id,
        title=title,
        type=type,
        status=status_val,
        source_url=source_url or None,
        description=description or None,
    )
    opp = create_opportunity(db, data)
    db.commit()
    return RedirectResponse(url=f"/opportunities/{opp.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/opportunities/{opportunity_id}", response_class=HTMLResponse)
def opportunity_detail_view(opportunity_id: int, request: Request, db: Session = Depends(get_db)):
    """Display opportunity details."""
    opp = get_opportunity(db, opportunity_id)
    if not opp:
        return RedirectResponse(url="/opportunities", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="opportunity_detail.html",
        context={
            "active_tab": "opportunities",
            "opportunity": opp,
        },
    )


# --- Contacts ---

@router.get("/contacts", response_class=HTMLResponse)
def contacts_list_view(
    request: Request,
    duplicate_flag: int | None = None,
    suppressed: int | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    """List contacts with filters."""
    contacts, _ = list_contacts(
        db,
        skip=0,
        limit=100,
        duplicate_flag=duplicate_flag,
        suppressed=suppressed,
        search=search,
    )
    dup_count = db.scalar(
        select(func.count()).select_from(Contact).where(Contact.duplicate_flag == 1)
    ) or 0

    return templates.TemplateResponse(
        request=request,
        name="contacts.html",
        context={
            "active_tab": "contacts",
            "contacts": contacts,
            "current_dup": duplicate_flag,
            "current_suppressed": suppressed,
            "duplicate_count": dup_count,
            "search": search,
        },
    )


@router.get("/contacts/new", response_class=HTMLResponse)
def contact_new_view(
    request: Request,
    company_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Form to create a new contact."""
    companies, _ = list_companies(db, skip=0, limit=200)
    return templates.TemplateResponse(
        request=request,
        name="contact_new.html",
        context={
            "active_tab": "contacts",
            "companies": companies,
            "selected_company_id": company_id,
        },
    )


@router.post("/contacts/new")
def contact_create_action(
    first_name: str = Form(...),
    last_name: str | None = Form(None),
    company_id: int | None = Form(None),
    headline: str | None = Form(None),
    linkedin_url: str | None = Form(None),
    email_address: str | None = Form(None),
    email_source: str = Form("manual"),
    phone_number: str | None = Form(None),
    phone_source: str = Form("manual"),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Handle new contact submission."""
    emails = []
    if email_address and email_address.strip():
        emails.append(EmailAddressCreate(address=email_address.strip(), is_primary=1, source=email_source))

    phones = []
    if phone_number and phone_number.strip():
        phones.append(PhoneNumberCreate(number=phone_number.strip(), is_primary=1, source=phone_source))

    data = ContactCreate(
        first_name=first_name,
        last_name=last_name or None,
        company_id=company_id or None,
        headline=headline or None,
        linkedin_url=linkedin_url or None,
        emails=emails,
        phones=phones,
        notes=notes or None,
    )
    contact, _ = create_contact(db, data)
    db.commit()
    return RedirectResponse(url=f"/contacts/{contact.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/contacts/{contact_id}", response_class=HTMLResponse)
def contact_detail_view(contact_id: int, request: Request, db: Session = Depends(get_db)):
    """Display contact profile, emails, phones, and duplicate review notice."""
    contact = get_contact(db, contact_id)
    if not contact:
        return RedirectResponse(url="/contacts", status_code=status.HTTP_303_SEE_OTHER)

    candidate = None
    if contact.duplicate_flag and contact.duplicate_of_contact_id:
        candidate = get_contact(db, contact.duplicate_of_contact_id)

    email_verifications = {}
    if contact.emails:
        for em in contact.emails:
            latest = sorted(em.verifications, key=lambda v: v.verified_at, reverse=True) if em.verifications else []
            email_verifications[em.id] = latest[0] if latest else None

    return templates.TemplateResponse(
        request=request,
        name="contact_detail.html",
        context={
            "active_tab": "contacts",
            "contact": contact,
            "candidate_contact": candidate,
            "email_verifications": email_verifications,
        },
    )


@router.post("/contacts/{contact_id}/suppress")
def contact_suppress_action(
    contact_id: int,
    suppressed: int = Form(...),
    reason: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Toggle contact-level suppression."""
    set_contact_suppression(db, contact_id, bool(suppressed), reason)
    db.commit()
    return RedirectResponse(url=f"/contacts/{contact_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/contacts/{contact_id}/emails")
def contact_add_email_action(
    contact_id: int,
    address: str = Form(...),
    source: str = Form("manual"),
    db: Session = Depends(get_db),
):
    """Add email address to contact with provenance."""
    data = EmailAddressCreate(address=address, source=source)
    add_email_address(db, contact_id, data)
    db.commit()
    return RedirectResponse(url=f"/contacts/{contact_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/contacts/{contact_id}/emails/{email_id}/suppress")
def contact_email_suppress_action(
    contact_id: int,
    email_id: int,
    suppressed: int = Form(...),
    reason: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Toggle email address suppression."""
    set_email_suppression(db, email_id, bool(suppressed), reason)
    db.commit()
    return RedirectResponse(url=f"/contacts/{contact_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/contacts/{contact_id}/emails/{email_id}/verify")
def contact_email_verify_action(
    contact_id: int,
    email_id: int,
    force: int = Form(0),
    db: Session = Depends(get_db),
):
    """Trigger Reoon verification or cache refresh for an email address."""
    try:
        verify_email_address(db, email_id, force=bool(force))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Error verifying email %d from UI: %s", email_id, e)
    return RedirectResponse(url=f"/contacts/{contact_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/contacts/{contact_id}/emails/{email_id}/approve-catchall")
def contact_email_approve_catchall_action(
    contact_id: int,
    email_id: int,
    db: Session = Depends(get_db),
):
    """Manually approve a verified catch-all address from UI."""
    try:
        approve_catch_all(db, email_id)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Error approving catch-all for email %d from UI: %s", email_id, e)
    return RedirectResponse(url=f"/contacts/{contact_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/contacts/{contact_id}/phones")
def contact_add_phone_action(
    contact_id: int,
    number: str = Form(...),
    type: str = Form("mobile"),
    source: str = Form("manual"),
    db: Session = Depends(get_db),
):
    """Add phone number with provenance."""
    data = PhoneNumberCreate(number=number, type=type, source=source)
    add_phone_number(db, contact_id, data)
    db.commit()
    return RedirectResponse(url=f"/contacts/{contact_id}", status_code=status.HTTP_303_SEE_OTHER)


# --- Multi-Level Suppressions View ---

@router.get("/suppressions", response_class=HTMLResponse)
def suppressions_view(request: Request, db: Session = Depends(get_db)):
    """Central view of all multi-level suppressed entities."""
    suppressed_companies = db.execute(
        select(Company).where(Company.suppressed == 1).order_by(Company.suppressed_at.desc())
    ).scalars().all()

    suppressed_contacts = db.execute(
        select(Contact)
        .options(selectinload(Contact.company))
        .where(Contact.suppressed == 1)
        .order_by(Contact.suppressed_at.desc())
    ).scalars().all()

    suppressed_emails = db.execute(
        select(EmailAddress)
        .options(selectinload(EmailAddress.contact))
        .where(EmailAddress.suppressed == 1)
        .order_by(EmailAddress.suppressed_at.desc())
    ).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="suppressions.html",
        context={
            "active_tab": "suppressions",
            "suppressed_companies": suppressed_companies,
            "suppressed_contacts": suppressed_contacts,
            "suppressed_emails": suppressed_emails,
        },
    )
