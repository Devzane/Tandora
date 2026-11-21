"""Contact, Role, EmailAddress, and PhoneNumber Pydantic Schemas."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


# --- Role Schemas ---
class ContactRoleBase(BaseModel):
    role: str = Field(..., min_length=1, max_length=100)


class ContactRoleCreate(ContactRoleBase):
    pass


class ContactRoleResponse(ContactRoleBase):
    id: int
    contact_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Email Address Schemas ---
class EmailAddressBase(BaseModel):
    address: str = Field(..., min_length=3, max_length=255)
    is_primary: int = 0
    source: str = Field("manual", description="'ContactOut', 'Apollo', 'LinkedIn', 'manual', 'website'")
    source_url: str | None = Field(None, max_length=1000)


class EmailAddressCreate(EmailAddressBase):
    pass


class EmailAddressSuppressionRequest(BaseModel):
    suppressed: bool
    reason: str | None = None


class EmailAddressResponse(EmailAddressBase):
    id: int
    external_id: str
    contact_id: int
    captured_at: datetime
    suppressed: int
    suppressed_reason: str | None = None
    suppressed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Phone Number Schemas ---
class PhoneNumberBase(BaseModel):
    number: str = Field(..., min_length=3, max_length=50)
    type: str = Field("direct", description="'mobile', 'work', 'direct', 'company', 'other'")
    source: str = Field("manual", description="'ContactOut', 'Apollo', 'LinkedIn', 'manual', 'website'")
    source_url: str | None = Field(None, max_length=1000)


class PhoneNumberCreate(PhoneNumberBase):
    pass


class PhoneNumberResponse(PhoneNumberBase):
    id: int
    contact_id: int
    captured_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Contact Schemas ---
class ContactBase(BaseModel):
    company_id: int | None = None
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    headline: str | None = Field(None, max_length=500)
    linkedin_url: str | None = Field(None, max_length=1000)
    notes: str | None = None


class ContactCreate(ContactBase):
    roles: list[ContactRoleCreate] = Field(default_factory=list)
    emails: list[EmailAddressCreate] = Field(default_factory=list)
    phones: list[PhoneNumberCreate] = Field(default_factory=list)


class ContactUpdate(BaseModel):
    company_id: int | None = None
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    headline: str | None = Field(None, max_length=500)
    linkedin_url: str | None = Field(None, max_length=1000)
    notes: str | None = None
    duplicate_flag: int | None = None
    duplicate_of_contact_id: int | None = None


class ContactSuppressionRequest(BaseModel):
    suppressed: bool
    reason: str | None = None


class ContactResponse(ContactBase):
    id: int
    external_id: str
    full_name: str | None = None
    normalized_linkedin_url: str | None = None
    duplicate_flag: int = 0
    duplicate_of_contact_id: int | None = None
    suppressed: int = 0
    suppressed_reason: str | None = None
    suppressed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    sheets_row_id: str | None = None
    sheets_last_synced_at: datetime | None = None

    roles: list[ContactRoleResponse] = Field(default_factory=list)
    emails: list[EmailAddressResponse] = Field(default_factory=list)
    phones: list[PhoneNumberResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
