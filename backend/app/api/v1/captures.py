"""Capture Ingestion REST API Router."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.capture import CapturePayload, CaptureResponse
from app.services.capture_service import ingest_capture

router = APIRouter(prefix="/captures", tags=["Captures"])


@router.post("/", response_model=CaptureResponse, status_code=status.HTTP_201_CREATED)
def ingest_capture_endpoint(payload: CapturePayload, db: Session = Depends(get_db)):
    """Ingest prospect capture from Chrome extension or web form."""
    try:
        response = ingest_capture(db, payload)
        return response
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
