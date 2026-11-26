"""Email Verification REST API Router."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import MissingCredentialError
from app.database import get_db
from app.integrations.reoon import ReoonAPIError
from app.schemas.email_verification import (
    CatchAllApprovalResponse,
    EmailVerificationResponse,
    VerificationStatsResponse,
)
from app.services.verification_service import (
    approve_catch_all,
    get_latest_verification,
    get_verification_stats,
    is_address_usable,
    verify_email_address,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Email Verification"])


@router.post(
    "/emails/{email_id}/verify",
    response_model=EmailVerificationResponse,
    status_code=status.HTTP_200_OK,
)
def verify_email_endpoint(
    email_id: int,
    force: bool = Query(False, description="Bypass 30-day cache and force a new Reoon API call"),
    db: Session = Depends(get_db),
):
    """Verify an email address deliverability or return cached verification."""
    try:
        verification, was_cached = verify_email_address(db, email_id, force=force)
        db.commit()

        usable, _ = is_address_usable(db, email_id)

        response = EmailVerificationResponse.model_validate(verification)
        response.was_cached = was_cached
        response.is_usable = usable
        return response
    except MissingCredentialError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ReoonAPIError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Reoon email verification service error: {e}",
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error verifying email %d", email_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal verification error: {e}",
        )


@router.post(
    "/emails/{email_id}/approve-catchall",
    response_model=CatchAllApprovalResponse,
    status_code=status.HTTP_200_OK,
)
def approve_catchall_endpoint(
    email_id: int,
    db: Session = Depends(get_db),
):
    """Manually approve a verified catch-all address for outreach drafting and sending."""
    try:
        verification = approve_catch_all(db, email_id)
        db.commit()
        return CatchAllApprovalResponse(
            email_address_id=verification.email_address_id,
            status=verification.status,
            catch_all_approved=verification.catch_all_approved,
            catch_all_approved_at=verification.catch_all_approved_at,
            message="Catch-all address successfully approved for outreach",
        )
    except ValueError as e:
        db.rollback()
        err_msg = str(e)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error approving catch-all for email %d", email_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error approving catch-all: {e}",
        )


@router.get(
    "/emails/{email_id}/verification",
    response_model=EmailVerificationResponse,
    status_code=status.HTTP_200_OK,
)
def get_email_verification_endpoint(
    email_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve the latest verification result for an email address."""
    verification = get_latest_verification(db, email_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No verification record found for email address ID {email_id}",
        )

    usable, _ = is_address_usable(db, email_id)
    response = EmailVerificationResponse.model_validate(verification)
    response.was_cached = True
    response.is_usable = usable
    return response


@router.get(
    "/verifications/stats",
    response_model=VerificationStatsResponse,
    status_code=status.HTTP_200_OK,
)
def get_verification_stats_endpoint(
    db: Session = Depends(get_db),
):
    """Retrieve aggregate email verification and API credit usage statistics."""
    stats = get_verification_stats(db)
    return VerificationStatsResponse(**stats)
