# Agent Instructions — Tandora Lead Management & Outreach Application

## Purpose

This document defines the operational rules for any AI coding agent implementing the Tandora application. These rules are mandatory. No agent may deviate from them without explicit user instruction.

---

## 1. Before Writing Any Code

### 1.1 Read the Documentation First

Before writing any code for a milestone, the agent must read:

1. `docs/PROJECT_SPECIFICATION.md` — Understand the requirements and constraints.
2. `docs/ARCHITECTURE.md` — Understand the system design and component responsibilities.
3. `docs/DATABASE_SCHEMA.md` — Understand the data model.
4. `docs/WORKFLOWS.md` — Understand the user workflows.
5. `docs/SECURITY_AND_COMPLIANCE.md` — Understand the security requirements.
6. `docs/IMPLEMENTATION_ROADMAP.md` — Identify the current milestone and its definition of done.

### 1.2 Load Relevant Skills

Before implementing each component, read the relevant skill files from the project skills directory:

| Component | Skill to Read |
|-----------|--------------|
| Python backend code | `skills/python-backend/SKILL.md` |
| FastAPI endpoints | `skills/fastapi-development/SKILL.md` |
| Database models and queries | `skills/sqlite-database/SKILL.md` |
| Chrome Extension | `skills/chrome-extension/SKILL.md` |
| Google Sheets integration | `skills/google-sheets-integration/SKILL.md` |
| Email verification | `skills/email-verification/SKILL.md` |
| LLM integration | `skills/llm-integration/SKILL.md` |
| Email sending/receiving | `skills/email-delivery/SKILL.md` |
| Testing | `skills/testing-and-quality/SKILL.md` |
| Security implementation | `skills/security-engineering/SKILL.md` |
| Git version control & atomic commits | `skills/git-workflow/SKILL.md` |

### 1.3 Inspect the Repository

Before writing code, inspect what already exists:
- List the files in the backend directory.
- Check which Alembic migrations have already been applied.
- Read existing model files to understand current schema state.
- Check existing service files to understand implemented patterns.
- Do not duplicate existing code.

---

## 2. During Implementation

### 2.1 Follow the Architecture

- Implement only the patterns described in `ARCHITECTURE.md`.
- Do not introduce new frameworks, libraries, or infrastructure components without explicit user approval.
- Do not replace SQLite with any other database.
- Do not introduce Supabase, Redis, Celery, Docker, or cloud services.
- Do not introduce a message queue where APScheduler was specified.

### 2.2 Implement Incrementally

- Implement one milestone at a time, as defined in `IMPLEMENTATION_ROADMAP.md`.
- Do not implement features from future milestones while working on the current one.
- If a future feature is easy to add now, do not add it. Document it as a note instead.

### 2.3 Never Change Agreed Requirements Silently

If you believe a requirement is unclear, contradictory, or technically problematic:
- **Stop**.
- **Report the issue clearly** to the user.
- **Do not silently interpret** the requirement in a way that changes its intent.
- **Do not simplify** a requirement without declaring that you are doing so.
- **Wait for clarification** before continuing.

### 2.4 Never Invent API Specifications

- Do not invent API endpoint structures not described in the documentation.
- Do not add request or response fields that were not specified.
- If the documentation is incomplete for a specific detail (e.g., exact field name), use the most obvious and consistent interpretation, then document your assumption clearly.
- Never invent external API responses. Use official documentation references only.

### 2.5 Never Hard-Code Credentials & Integration-Specific Validation

- All credentials must come from environment variables loaded via `python-dotenv`.
- Never put a real API key, password, or token in any source file or committed artifact.
- The application must start cleanly without requiring every external API credential upfront.
- External integrations must validate their required credentials lazily/on-demand when an operation requires them.
- Missing credentials must produce clear, actionable error messages explaining which variable is missing.
- Unconfigured integrations must never prevent unrelated application functionality from working.
- Document all environment variable names in `.env.example` without real credentials.

### 2.6 Use Type Hints Everywhere

- All Python functions must have type hints for all parameters and return values.
- Use Pydantic models for all API request and response schemas.
- Do not use `Any` type unless absolutely unavoidable, and document why.

### 2.7 Handle Errors Explicitly

- Do not use bare `except:` clauses.
- Catch specific exceptions.
- Return informative error responses from API endpoints.
- Write audit log entries for all failures that affect outreach state.

### 2.8 Write Tests with Every Feature

- Tests must be written in the same milestone as the feature.
- Do not defer testing to a later milestone.
- Mock all external services in tests (Reoon, Gemini, Ollama, Zoho SMTP/IMAP, Google Sheets).
- Never make real API calls in automated tests.

---

## 3. After Completing a Milestone

### 3.1 Stop and Report

When a milestone is complete:
1. Run all tests. Report the results.
2. Report exactly what was implemented.
3. Report any deviations from the milestone plan (even minor ones).
4. Report any assumptions you made.
5. Report any open questions or issues discovered.
6. **Stop**. Do not begin the next milestone.

### 3.2 Honest Reporting

Report the state of implementation honestly:
- If a feature is partially implemented, say so.
- If a test is passing but incomplete, say so.
- If you made a simplification, say so.
- Do not claim a milestone is complete unless all acceptance criteria are met.

### 3.3 Definition of Done

A milestone is complete when:
- All acceptance criteria in `IMPLEMENTATION_ROADMAP.md` are satisfied.
- All tests for the milestone pass.
- No regression: all tests from previous milestones still pass.
- The code is committed (or staged) with a clear commit message referencing the milestone.

---

## 4. Specific Rules for This Application

### 4.1 The Approval Gate Is Inviolable

The system must never send an email without a recorded `approvals` record in the database that references the specific draft version being sent. This check must run in code every time, not just in comments.

### 4.2 Daily Quota Is Enforced at the Database Level

Count today's outreach events from the `outreach_events` table (not an in-memory counter) before every send. This ensures the quota survives process restarts.

### 4.3 Catch-all Addresses Require Explicit Approval

Before using a `catch-all` address for drafting or sending, check `email_verifications.catch_all_approved = 1`. If it is `0`, block the operation. Do not silently allow catch-all addresses.

### 4.4 One Thread Per Contact Per Opportunity

The unique constraint on `outreach_threads(opportunity_id, contact_id)` must be enforced in both the database schema and the service layer. If a thread already exists, return the existing thread ID.

### 4.5 Audit Log Is Append-Only

No code path may execute an UPDATE or DELETE on `audit_log`. If you accidentally write such code, remove it immediately.

### 4.6 Backend Binds to Localhost Only

The uvicorn server must bind to `127.0.0.1`, not `0.0.0.0`. This is a security requirement.

### 4.7 SQLite Foreign Keys Must Be Enabled

After creating the SQLite engine, execute `PRAGMA foreign_keys = ON` in every session. Without this, SQLite ignores foreign key constraints.

### 4.8 Pre-Send Validation (10 Mandatory Checks)

Every outbound email dispatch must verify all 10 conditions against persistent database records before transmission:
1. Exact version approval (`approvals.draft_id == draft.id`).
2. Global pause disabled (`app_config.sending_paused == 'false'`).
3. Global daily quota available (< 20 emails counted from `outreach_events`).
4. Contact not suppressed (`contacts.suppressed == 0`).
5. Selected address not suppressed (no hard bounce in `bounces`).
6. Email address meets verification eligibility (`email_verifications.status` is safe or approved catch-all).
7. Catch-all address has separate explicit approval (`catch_all_approved == 1`).
8. Recipient is not a duplicate of an already processed outbound message.
9. Outreach thread is still eligible for sending (`outreach_threads.status` is active and sendable).
10. Message content has not changed since approval.

If any check fails, abort sending and record the reason in `audit_log`. Never rely exclusively on in-memory state.

### 4.9 Canonical Database Entities and Suppression Standard

Follow `docs/DATABASE_SCHEMA.md` as the authoritative source:
- The audit table is `audit_log` (singular, never `audit_logs`).
- There is no separate `suppression_list` table. Suppression is tracked directly via `contacts.suppressed`, `contacts.suppressed_reason`, `contacts.suppressed_at`, and `outreach_threads.status = 'suppressed'`.

---

## 5. What to Do When Blocked

If you are blocked on a milestone due to:
- A missing environment variable (live API key not yet configured).
- An unclear requirement.
- A technical constraint not anticipated in the documentation.

Then:
1. Document the blocker clearly.
2. Implement whatever can be implemented without resolving the blocker.
3. Create a test that uses a mock for the blocked dependency.
4. Report the blocker and await user input.
5. Do not invent a workaround that changes the agreed architecture.

---

## 6. Code Style and Quality Standards

- Follow PEP 8 and use a consistent code formatter (Black or Ruff).
- Maximum line length: 100 characters.
- Imports must be sorted (use isort or Ruff's import sorting).
- All public functions and classes must have docstrings.
- Module-level docstrings must describe the module's purpose.
- No dead code, no commented-out code left in committed files.
- No `print()` statements in production code. Use the Python `logging` module.
