"""Contact REST API Router."""

from math import ceil
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.contact import (
    ContactCreate,
    ContactUpdate,
    ContactResponse,
    ContactSuppressionRequest,
    ContactRoleCreate,
    ContactRoleResponse,
    EmailAddressCreate,
    EmailAddressResponse,
    EmailAddressSuppressionRequest,
    PhoneNumberCreate,
    PhoneNumberResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.contact_service import (
    create_contact,
    get_contact,
    list_contacts,
    update_contact,
    set_contact_suppression,
    add_email_address,
    set_email_suppression,
    add_phone_number,
    add_contact_role,
)

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("/", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact_endpoint(payload: ContactCreate, db: Session = Depends(get_db)):
    """Create or merge a contact with deduplication."""
    try:
        contact, _ = create_contact(db, payload)
        db.commit()
        refreshed = get_contact(db, contact.id)
        return refreshed
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=PaginatedResponse[ContactResponse])
def list_contacts_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    company_id: int | None = None,
    suppressed: int | None = None,
    duplicate_flag: int | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    """List contacts with filters and pagination."""
    skip = (page - 1) * size
    items, total = list_contacts(
        db,
        skip=skip,
        limit=size,
        company_id=company_id,
        suppressed=suppressed,
        duplicate_flag=duplicate_flag,
        search=search,
    )
    pages = ceil(total / size) if size > 0 else 0
    return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.get("/{contact_id}", response_model=ContactResponse)
def get_contact_endpoint(contact_id: int, db: Session = Depends(get_db)):
    """Retrieve full details for a contact."""
    contact = get_contact(db, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.patch("/{contact_id}", response_model=ContactResponse)
def update_contact_endpoint(contact_id: int, payload: ContactUpdate, db: Session = Depends(get_db)):
    """Update contact attributes."""
    contact = update_contact(db, contact_id, payload)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    db.commit()
    refreshed = get_contact(db, contact_id)
    return refreshed


@router.post("/{contact_id}/suppress", response_model=ContactResponse)
def set_contact_suppression_endpoint(
    contact_id: int, payload: ContactSuppressionRequest, db: Session = Depends(get_db)
):
    """Toggle contact-level suppression and cancel pending follow-ups."""
    contact = set_contact_suppression(db, contact_id, payload.suppressed, payload.reason)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    db.commit()
    refreshed = get_contact(db, contact_id)
    return refreshed


@router.post("/{contact_id}/roles", response_model=ContactRoleResponse, status_code=status.HTTP_201_CREATED)
def add_role_endpoint(contact_id: int, payload: ContactRoleCreate, db: Session = Depends(get_db)):
    """Attach a role to a contact."""
    contact = get_contact(db, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    role = add_contact_role(db, contact_id, payload)
    db.commit()
    db.refresh(role)
    return role


@router.post("/{contact_id}/emails", response_model=EmailAddressResponse, status_code=status.HTTP_201_CREATED)
def add_email_endpoint(contact_id: int, payload: EmailAddressCreate, db: Session = Depends(get_db)):
    """Attach an email address with provenance to a contact."""
    contact = get_contact(db, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    try:
        email_obj = add_email_address(db, contact_id, payload)
        db.commit()
        db.refresh(email_obj)
        return email_obj
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{contact_id}/emails/{email_id}/suppress", response_model=EmailAddressResponse)
def set_email_suppression_endpoint(
    contact_id: int, email_id: int, payload: EmailAddressSuppressionRequest, db: Session = Depends(get_db)
):
    """Toggle address-level suppression."""
    email_obj = set_email_suppression(db, email_id, payload.suppressed, payload.reason)
    if not email_obj or email_obj.contact_id != contact_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email address not found")
    db.commit()
    db.refresh(email_obj)
    return email_obj


@router.post("/{contact_id}/phones", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
def add_phone_endpoint(contact_id: int, payload: PhoneNumberCreate, db: Session = Depends(get_db)):
    """Attach a phone number with provenance to a contact."""
    contact = get_contact(db, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    try:
        phone = add_phone_number(db, contact_id, payload)
        db.commit()
        db.refresh(phone)
        return phone
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
