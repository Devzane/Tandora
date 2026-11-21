"""Capture Pydantic Schemas for Ingestion."""

from typing import Any
from pydantic import BaseModel, Field
from app.schemas.contact import ContactRoleCreate, EmailAddressCreate, PhoneNumberCreate


class CompanyCaptureInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    website: str | None = None
    industry: str | None = None
    description: str | None = None
    type: str = "employer"
    source_url: str | None = None


class OpportunityCaptureInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    type: str = "employment"
    source_url: str | None = None


class ContactCaptureInput(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = None
    headline: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    roles: list[ContactRoleCreate] = Field(default_factory=list)
    emails: list[EmailAddressCreate] = Field(default_factory=list)
    phones: list[PhoneNumberCreate] = Field(default_factory=list)


class CapturePayload(BaseModel):
    source_type: str = Field(..., description="'extension_dom', 'extension_manual_paste', 'web_form', 'sheets_sync'")
    source_url: str | None = None
    company: CompanyCaptureInput | None = None
    opportunity: OpportunityCaptureInput | None = None
    contact: ContactCaptureInput | None = None
    raw_payload: dict[str, Any] | None = None


class CaptureResponse(BaseModel):
    capture_id: int
    company_id: int | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    duplicate_flag: int = 0
    message: str
