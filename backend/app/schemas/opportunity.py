"""Opportunity Pydantic Schemas."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class OpportunityBase(BaseModel):
    company_id: int
    type: str = Field("employment", description="'employment' or 'freelance_prospect'")
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    source_url: str | None = Field(None, max_length=1000)
    status: str = Field("active", description="'active', 'paused', 'closed', 'won', 'lost'")


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    type: str | None = None
    source_url: str | None = Field(None, max_length=1000)
    status: str | None = None


class OpportunityResponse(OpportunityBase):
    id: int
    external_id: str
    created_at: datetime
    updated_at: datetime
    sheets_row_id: str | None = None
    sheets_last_synced_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OpportunityContactResponse(BaseModel):
    id: int
    opportunity_id: int
    contact_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

