"""Company / Organization REST API Router."""

from math import ceil
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanySuppressionRequest,
)
from app.schemas.common import PaginatedResponse
from app.services.organization_service import (
    create_company,
    get_company,
    list_companies,
    update_company,
    set_company_suppression,
)

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company_endpoint(payload: CompanyCreate, db: Session = Depends(get_db)):
    """Create a new company record."""
    try:
        company = create_company(db, payload)
        db.commit()
        db.refresh(company)
        return company
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=PaginatedResponse[CompanyResponse])
def list_companies_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    type: str | None = None,
    suppressed: int | None = None,
    db: Session = Depends(get_db),
):
    """List companies with pagination and filters."""
    skip = (page - 1) * size
    items, total = list_companies(db, skip=skip, limit=size, type=type, suppressed=suppressed)
    pages = ceil(total / size) if size > 0 else 0
    return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company_endpoint(company_id: int, db: Session = Depends(get_db)):
    """Retrieve details for a specific company."""
    company = get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyResponse)
def update_company_endpoint(company_id: int, payload: CompanyUpdate, db: Session = Depends(get_db)):
    """Update details for a specific company."""
    company = update_company(db, company_id, payload)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    db.commit()
    db.refresh(company)
    return company


@router.post("/{company_id}/suppress", response_model=CompanyResponse)
def set_company_suppression_endpoint(
    company_id: int, payload: CompanySuppressionRequest, db: Session = Depends(get_db)
):
    """Toggle company suppression and cascade-cancel follow-ups for employed contacts."""
    company = set_company_suppression(db, company_id, payload.suppressed, payload.reason)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    db.commit()
    db.refresh(company)
    return company
