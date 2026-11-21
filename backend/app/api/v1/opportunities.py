"""Opportunity REST API Router."""

from math import ceil
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.opportunity import (
    OpportunityCreate,
    OpportunityUpdate,
    OpportunityResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.organization_service import (
    create_opportunity,
    get_opportunity,
    list_opportunities,
    update_opportunity,
)

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


@router.post("/", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
def create_opportunity_endpoint(payload: OpportunityCreate, db: Session = Depends(get_db)):
    """Create a new opportunity."""
    try:
        opportunity = create_opportunity(db, payload)
        db.commit()
        db.refresh(opportunity)
        return opportunity
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=PaginatedResponse[OpportunityResponse])
def list_opportunities_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    company_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """List opportunities with pagination and optional filters."""
    skip = (page - 1) * size
    items, total = list_opportunities(db, skip=skip, limit=size, company_id=company_id, status=status_filter)
    pages = ceil(total / size) if size > 0 else 0
    return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity_endpoint(opportunity_id: int, db: Session = Depends(get_db)):
    """Retrieve details for a specific opportunity."""
    opportunity = get_opportunity(db, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return opportunity


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
def update_opportunity_endpoint(
    opportunity_id: int, payload: OpportunityUpdate, db: Session = Depends(get_db)
):
    """Update details for an opportunity."""
    opportunity = update_opportunity(db, opportunity_id, payload)
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    db.commit()
    db.refresh(opportunity)
    return opportunity
