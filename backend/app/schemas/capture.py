"""Capture Pydantic Schemas for Ingestion."""

from datetime import datetime
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
    location: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    roles: list[ContactRoleCreate] = Field(default_factory=list)
    emails: list[EmailAddressCreate] = Field(default_factory=list)
    phones: list[PhoneNumberCreate] = Field(default_factory=list)


class PostCaptureInput(BaseModel):
    author_name: str = Field(..., min_length=1, max_length=200)
    author_linkedin_url: str | None = Field(None, max_length=1000)
    author_headline: str | None = Field(None, max_length=500)
    post_url: str = Field(..., min_length=1, max_length=1000)
    post_text: str = Field(..., min_length=1)
    post_timestamp: str | None = Field(None, max_length=100)
    company_mentioned: str | None = Field(None, max_length=255)
    create_author_contact: bool = True


class CapturePayload(BaseModel):
    capture_type: str = Field("linkedin_profile", description="'linkedin_profile', 'linkedin_post', 'linkedin_company', 'job_listing', 'generic_web', 'contactout_apollo_overlay', 'extension_dom', 'extension_manual_paste'")
    source_type: str | None = Field(None, description="Alias or fallback for capture_type")
    page_type: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    selected_text: str | None = None
    user_notes: str | None = None
    captured_at: datetime | None = None
    company: CompanyCaptureInput | None = None
    opportunity: OpportunityCaptureInput | None = None
    contact: ContactCaptureInput | None = None
    post: PostCaptureInput | None = None
    raw_payload: dict[str, Any] | None = None


class CaptureResponse(BaseModel):
    capture_id: int
    company_id: int | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    post_id: int | None = None
    duplicate_flag: int = 0
    message: str
