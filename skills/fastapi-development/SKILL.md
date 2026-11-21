---
name: fastapi-development
description: FastAPI application structure, Pydantic validation, authentication, dependency injection, and API testing for Tandora.
risk: low
source: project
date_added: '2026-11-21'
---

# FastAPI Development Skill — Tandora

## Purpose

This skill covers building the Tandora FastAPI backend: router structure, Pydantic schemas, dependency injection, extension authentication, and API testing.

## When to Use

Read this skill before writing any FastAPI router, Pydantic schema, or API test.

## Required Engineering Practices

### Application Structure

```python
# app/main.py
from fastapi import FastAPI
from app.api.v1 import companies, contacts, opportunities, drafts
from app.database import create_db_and_tables

app = FastAPI(title="Tandora API", version="1.0.0")

app.include_router(companies.router, prefix="/api/v1/companies", tags=["companies"])
app.include_router(contacts.router, prefix="/api/v1/contacts", tags=["contacts"])

@app.on_event("startup")
async def startup():
    create_db_and_tables()
```

### Pydantic Schemas

- Create separate `Create`, `Update`, and `Response` schemas for each entity.
- Never return SQLAlchemy model objects directly. Always convert to Pydantic response schemas.
- Use `model_config = ConfigDict(from_attributes=True)` on response schemas for ORM compatibility.

```python
from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime

class ContactCreate(BaseModel):
    first_name: str
    last_name: str | None = None
    linkedin_url: str | None = None

class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: str | None
    created_at: datetime
```

### Dependency Injection

```python
# app/database.py
from sqlalchemy.orm import Session
from typing import Generator

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

```python
# In routers
from fastapi import Depends
from app.database import get_db

@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)):
    ...
```

### Extension Authentication

All endpoints consumed by the Chrome Extension must validate the shared secret:

```python
# app/dependencies/auth.py
from fastapi import Header, HTTPException
from app.config import get_settings

def verify_extension_secret(x_extension_secret: str = Header(...)):
    settings = get_settings()
    if x_extension_secret != settings.extension_api_secret:
        raise HTTPException(status_code=401, detail="Invalid extension secret")
```

### HTTP Status Codes

- 200: Successful read.
- 201: Successful create.
- 400: Bad request (invalid input).
- 401: Unauthorized (missing or invalid secret).
- 403: Forbidden (operation not permitted, e.g., no approval).
- 404: Resource not found.
- 409: Conflict (duplicate record, constraint violation).
- 422: Validation error (Pydantic handles this automatically).
- 500: Internal server error (unexpected failures only).

### Error Response Format

```python
from fastapi import HTTPException

raise HTTPException(
    status_code=409,
    detail={"error": "duplicate_contact", "message": "A contact with this name already exists at this company."}
)
```

## Implementation Guidelines

1. Keep routers thin. Delegate all logic to services.
2. Use `response_model` on all endpoints to ensure schema validation on output.
3. Use `status_code=201` on creation endpoints.
4. Use path parameters for resource IDs. Use query parameters for filters and pagination.
5. Use `APIRouter` with a prefix. Never define routes directly on the `app` object.

## Common Mistakes

- Putting database queries or business logic in routers. → Move to services.
- Not using `response_model`. → Always declare it.
- Returning SQLAlchemy objects directly. → Always convert to Pydantic.
- Forgetting `Depends(get_db)` and using a global session. → Use dependency injection.
- Using synchronous endpoints when calling async services. → Be consistent with sync/async.

## Security Considerations

- The FastAPI server must bind to `127.0.0.1` only. Configure in startup: `uvicorn app.main:app --host 127.0.0.1`.
- Do not expose a `/docs` endpoint in production if it reveals sensitive schema details.
- Validate all path and query parameters. Use `int` types for IDs (FastAPI rejects non-integers automatically).

## Testing Requirements

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_company():
    response = client.get("/api/v1/companies/1")
    assert response.status_code == 200
    assert response.json()["name"] == "Acme Corp"

def test_extension_auth_required():
    response = client.post("/api/v1/captures", json={...})
    assert response.status_code == 401
```

- Use `TestClient` for synchronous endpoint tests.
- Use an in-memory test database via a `pytest` fixture that overrides `get_db`.
- Test authentication on every protected endpoint.

## Project-Specific Constraints

- API prefix must be `/api/v1/` on all endpoints.
- All audit log writes happen in the service layer, not in routers.
- The `/api/v1/captures` endpoint requires the `X-Extension-Secret` header.
- The `/health` endpoint requires no authentication.
