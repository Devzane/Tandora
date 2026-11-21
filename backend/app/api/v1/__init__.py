"""API v1 Package Router."""

from fastapi import APIRouter
from app.api.v1.companies import router as companies_router
from app.api.v1.opportunities import router as opportunities_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.captures import router as captures_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(companies_router)
api_v1_router.include_router(opportunities_router)
api_v1_router.include_router(contacts_router)
api_v1_router.include_router(captures_router)

__all__ = ["api_v1_router"]
