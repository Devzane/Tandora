"""Pydantic Schemas Package."""

from app.schemas.common import PaginatedResponse, StandardMessageResponse
from app.schemas.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanySuppressionRequest,
)
from app.schemas.opportunity import (
    OpportunityCreate,
    OpportunityUpdate,
    OpportunityResponse,
)
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
from app.schemas.capture import (
    CapturePayload,
    CaptureResponse,
    CompanyCaptureInput,
    OpportunityCaptureInput,
    ContactCaptureInput,
)

__all__ = [
    "PaginatedResponse",
    "StandardMessageResponse",
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyResponse",
    "CompanySuppressionRequest",
    "OpportunityCreate",
    "OpportunityUpdate",
    "OpportunityResponse",
    "ContactCreate",
    "ContactUpdate",
    "ContactResponse",
    "ContactSuppressionRequest",
    "ContactRoleCreate",
    "ContactRoleResponse",
    "EmailAddressCreate",
    "EmailAddressResponse",
    "EmailAddressSuppressionRequest",
    "PhoneNumberCreate",
    "PhoneNumberResponse",
    "CapturePayload",
    "CaptureResponse",
    "CompanyCaptureInput",
    "OpportunityCaptureInput",
    "ContactCaptureInput",
]
