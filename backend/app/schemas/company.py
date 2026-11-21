"""Company / Organization Pydantic Schemas."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, max_length=255)
    description: str | None = None
    type: str = Field("employer", description="'employer' or 'freelance_prospect'")
    source_url: str | None = Field(None, max_length=1000)


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    website: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, max_length=255)
    description: str | None = None
    type: str | None = None
    source_url: str | None = Field(None, max_length=1000)


class CompanySuppressionRequest(BaseModel):
    suppressed: bool
    reason: str | None = None


class CompanyResponse(CompanyBase):
    id: int
    external_id: str
    suppressed: int
    suppressed_reason: str | None = None
    suppressed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    sheets_row_id: str | None = None
    sheets_last_synced_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
