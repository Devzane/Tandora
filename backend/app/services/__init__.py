"""Services Package."""

from app.services.audit_service import write_audit_log
from app.services.deduplication_service import (
    normalize_linkedin_url,
    normalize_email,
    find_existing_contact,
)
from app.services.organization_service import (
    create_company,
    get_company,
    list_companies,
    update_company,
    set_company_suppression,
    create_opportunity,
    get_opportunity,
    list_opportunities,
    update_opportunity,
)
from app.services.contact_service import (
    create_contact,
    get_contact,
    list_contacts,
    update_contact,
    set_contact_suppression,
    add_email_address,
    set_email_suppression,
    add_phone_number,
    add_contact_role,
)
from app.services.capture_service import ingest_capture
from app.services.verification_service import (
    verify_email_address,
    approve_catch_all,
    get_cached_verification,
    get_latest_verification,
    is_address_usable,
    get_verification_stats,
    map_reoon_status,
)

__all__ = [
    "write_audit_log",
    "normalize_linkedin_url",
    "normalize_email",
    "find_existing_contact",
    "create_company",
    "get_company",
    "list_companies",
    "update_company",
    "set_company_suppression",
    "create_opportunity",
    "get_opportunity",
    "list_opportunities",
    "update_opportunity",
    "create_contact",
    "get_contact",
    "list_contacts",
    "update_contact",
    "set_contact_suppression",
    "add_email_address",
    "set_email_suppression",
    "add_phone_number",
    "add_contact_role",
    "ingest_capture",
    "verify_email_address",
    "approve_catch_all",
    "get_cached_verification",
    "get_latest_verification",
    "is_address_usable",
    "get_verification_stats",
    "map_reoon_status",
]
