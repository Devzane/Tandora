"""Email Verification Pydantic Schemas."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class EmailVerificationBase(BaseModel):
    email_address_id: int
    status: str
    catch_all_approved: int = 0
    catch_all_approved_at: datetime | None = None
    credits_used: int = Field(default=1, description="Local net-credit estimate consumed by this verification.")
    verified_at: datetime
    expires_at: datetime


class EmailVerificationResponse(EmailVerificationBase):
    id: int
    was_cached: bool = False
    is_usable: bool = False

    model_config = ConfigDict(from_attributes=True)


class CatchAllApprovalResponse(BaseModel):
    email_address_id: int
    status: str
    catch_all_approved: int
    catch_all_approved_at: datetime | None = None
    message: str = "Catch-all address successfully approved for outreach"

    model_config = ConfigDict(from_attributes=True)


class VerificationStatsResponse(BaseModel):
    total_verifications: int
    total_credits_used: int = Field(
        default=0,
        description="Local net-credit estimate consumed based on verification outcomes. Reoon account balance serves as external reconciliation source.",
    )
    status_breakdown: dict[str, int] = Field(default_factory=dict)
    unapproved_catchalls: int = 0
    suppressed_by_verification: int = 0
    approved_active_count: int = 0
