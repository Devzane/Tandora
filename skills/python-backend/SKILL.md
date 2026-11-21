---
name: python-backend
description: Python best practices for the Tandora backend — modular architecture, type hints, error handling, logging, and configuration management.
risk: low
source: project
date_added: '2026-11-21'
---

# Python Backend Skill — Tandora

## Purpose

This skill governs all Python code written for the Tandora backend. It enforces the engineering practices required for a maintainable, correct, and secure single-user application.

## When to Use

Read this skill before writing any Python module in the `backend/` directory.

## Required Engineering Practices

### Project Structure

```
backend/
├── app/
│   ├── main.py           # FastAPI app instance, startup, middleware
│   ├── config.py         # Settings class, env var loading
│   ├── database.py       # SQLAlchemy engine, session factory
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── api/v1/           # FastAPI routers
│   ├── services/         # Business logic (no direct DB in routers)
│   ├── integrations/     # External service clients
│   └── providers/        # LLM provider abstraction
├── tests/
├── alembic/
└── pyproject.toml
```

### Type Hints

- All function parameters and return types must be annotated.
- Use `from __future__ import annotations` for forward references.
- Use `Optional[X]` or `X | None` for nullable values (prefer `X | None` in Python 3.10+).
- Do not use `Any` unless strictly necessary. Document every `Any` with a comment.

### Error Handling

- Never use bare `except:` clauses.
- Catch the most specific exception available.
- Use custom exception classes for domain errors (e.g., `ContactSuppressedException`).
- In services, raise exceptions. In API routers, convert them to HTTP responses.
- Use FastAPI's `HTTPException` for API error responses.

### Logging

- Use Python's built-in `logging` module.
- Configure logging in `app/main.py` at startup.
- Each module gets its own logger: `logger = logging.getLogger(__name__)`.
- Never use `print()` in production code.
- Log levels: DEBUG for diagnostics, INFO for normal operations, WARNING for recoverable issues, ERROR for failures.
- Do not log credentials, full email bodies, or personal data at DEBUG level in production.

### Configuration

- All configuration loaded via `pydantic-settings` `BaseSettings` class in `app/config.py`.
- Settings are populated from environment variables via `python-dotenv`.
- Integration credentials (API keys, SMTP passwords) are optional at startup so the application boots cleanly without all services configured.
- Integrations validate their required credentials on-demand upon invocation, failing with clear, actionable errors if missing.
- Non-sensitive settings have sensible defaults.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_path: str = "./data/tandora.db"
    daily_sending_limit: int = 20
    llm_provider: str = "gemini"
    
    # External integration credentials (validated on-demand)
    gemini_api_key: str | None = None
    reoon_api_key: str | None = None
    zoho_smtp_username: str | None = None
    zoho_smtp_password: str | None = None

    class Config:
        env_file = ".env"
```

### Separation of Concerns

- FastAPI routers handle HTTP: request parsing, response formatting, HTTP errors.
- Services handle business logic: validation, orchestration, calling integrations.
- Integration modules handle external service calls: one module per external service.
- Models handle database structure: no business logic in models.
- Never put database queries directly in routers.

## Implementation Guidelines

1. Use `get_db()` dependency injection for database sessions in routers.
2. Use SQLAlchemy 2.x style: `select()`, `session.execute()`, `session.scalar()`.
3. Use `with session.begin():` for transactions that must be atomic.
4. Keep functions small. If a function exceeds 40 lines, split it.
5. Use dataclasses or Pydantic models to pass structured data between layers.

## Common Mistakes

- Writing database queries directly in routers. → Move to services.
- Catching `Exception` broadly and silently swallowing errors. → Catch specifically, log, re-raise or convert.
- Storing credentials in `config.py` as literals. → Use env vars only.
- Using mutable default arguments. → Use `None` defaults and initialize inside the function.
- Not closing database sessions. → Always use FastAPI dependency injection with `yield`.

## Security Considerations

- Do not log sensitive data (email addresses, API keys, full message bodies) at DEBUG level.
- Do not expose internal error details in HTTP 500 responses. Log the detail, return a generic message.
- Validate all inputs through Pydantic before they reach service layer.

## Testing Requirements

- Use `pytest` and `pytest-asyncio` for async tests.
- Use `pytest` fixtures for database sessions (use a test-specific in-memory SQLite database).
- Use `unittest.mock` or `pytest-mock` for mocking external services.
- Test the service layer independently of the API layer.
- Minimum: one happy-path test and one error-path test per service function.

## Project-Specific Constraints

- SQLite only. No ORM operations that require PostgreSQL-specific features.
- `PRAGMA foreign_keys = ON` must be set after every connection.
- Audit log entries must be written as side effects of key service operations.
- The `audit_log` table is append-only. No UPDATE or DELETE.
