# Agent Instructions — Tandora Lead Management & Outreach Application

## Purpose

This document defines the mandatory operational rules, engineering constraints, and verification protocols for any AI coding agent working on the Tandora application.

---

## 1. Before Writing Any Code

### 1.1 Read Project Documentation in Strict Sequence
Before writing or modifying any code for an implementation stage, the agent must read:

1. `docs/PROJECT_SPECIFICATION.md` — Core requirements, constraints, and acceptance criteria.
2. `docs/ARCHITECTURE.md` — System architecture, components, and data flows.
3. `docs/DATABASE_SCHEMA.md` — Authoritative 21-table schema, integrity rules, and deduplication standards.
4. `docs/WORKFLOWS.md` — 12 end-to-end user and system workflows.
5. `docs/SECURITY_AND_COMPLIANCE.md` — Secrets management, SHA-256 approval hashing, send attempts, and compliance.
6. `docs/IMPLEMENTATION_ROADMAP.md` — 10 practical implementation stages (Stages 0 to 9).

### 1.2 Load Relevant Skills
Before implementing any component, read the relevant skill from `skills/` relative to the workspace root:

| Component / Task | Project Skill File |
|------------------|--------------------|
| Python backend architecture & coding standards | `skills/python-backend/SKILL.md` |
| FastAPI routers, templates, dependencies & testing | `skills/fastapi-development/SKILL.md` |
| SQLite, SQLAlchemy 2.x, Alembic & transactions | `skills/sqlite-database/SKILL.md` |
| Chrome Extension Manifest V3 & DOM capture | `skills/chrome-extension/SKILL.md` |
| Google Sheets API v4 bidirectional sync & conflicts | `skills/google-sheets-integration/SKILL.md` |
| Reoon API email verification & catch-all gating | `skills/email-verification/SKILL.md` |
| LLM provider abstraction (Gemini & Ollama) & drafting | `skills/llm-integration/SKILL.md` |
| Zoho SMTP sending, IMAP monitoring & rate limits | `skills/email-delivery/SKILL.md` |
| Pytest test suites, mocking & quality assurance | `skills/testing-and-quality/SKILL.md` |
| Security engineering, suppression & audit controls | `skills/security-engineering/SKILL.md` |
| Git version control, atomic commits & branch hygiene | `skills/git-workflow/SKILL.md` |

### 1.3 Inspect Workspace Dynamically
- Discover the repository root dynamically from the currently opened workspace.
- Check existing directories and code in `backend/` and `extension/`.
- Check applied Alembic migrations in `backend/alembic/versions/`.
- Check existing automated tests in `backend/tests/`.
- Avoid hardcoded Windows paths or username assumptions.

---

## 2. During Implementation

### 2.1 Follow the Documented Architecture
- Implement strictly the patterns described in `ARCHITECTURE.md`.
- Never introduce technologies outside the agreed stack: no Supabase, PostgreSQL, Docker, Redis, Celery, Kubernetes, or cloud hosting.
- The FastAPI application must bind strictly to `127.0.0.1:8000`.

### 2.2 Implement One Stage at a Time
- Implement only the current approved stage as defined in `IMPLEMENTATION_ROADMAP.md`.
- Never jump ahead to future stages.
- Never implement features across multiple stages in a single turn.

### 2.3 Never Invent API Specifications or Behavior
- Follow official API documentation for Reoon, Zoho SMTP/IMAP, Gemini, and Google Sheets.
- Do not invent undocumented query parameters, response keys, or mock structures.
- If an API detail is unverified, document it as an assumption and seek confirmation.

### 2.4 Credential Management & On-Demand Validation
- All credentials must be loaded from environment variables via `python-dotenv`.
- Never put real API keys, passwords, or tokens in source files or committed artifacts.
- The application must boot cleanly without requiring all external service credentials upfront.
- Integrations must validate their specific credentials lazily/on-demand when an operation requires them.
- Missing credentials must return a clear, actionable error message.
- Unconfigured integrations must never block unrelated application functionality.

### 2.5 Approval Integrity & SHA-256 Hashing
- Never bypass the manual approval gate.
- Approvals must calculate and store a SHA-256 hash over: `recipient_address + "\n" + subject + "\n" + body + "\n" + str(draft_id) + "\n" + str(version)`.
- Immediately before sending, the delivery engine must re-calculate the hash and verify an exact match.
- Any draft edit creates a new version (`is_edited = 1`), invalidating previous approvals.

### 2.6 Delivery Reliability & Persistent Send Attempts
- Every outbound send must follow the persistent lifecycle: `pending` $\rightarrow$ `sending` $\rightarrow$ `sent` / `failed` / `unknown`.
- Persist the `send_attempts` record and commit the database transaction *before* contacting SMTP.
- Never auto-resend an `unknown` send attempt; require manual reconciliation.
- Enforce unique idempotency keys per thread action.
- Serialize outbound send operations to protect the 20-message daily quota and prevent concurrent duplicate sends.
- Default to `DRY_RUN = true` until live sending is explicitly enabled by configuration.

### 2.7 Write Tests with Every Feature
- Write unit, API, and integration tests in the same stage as the feature.
- Mock all external services (Reoon, Gemini, Ollama, Zoho SMTP/IMAP, Google Sheets). Never make real network calls in automated tests.
- Verify that previous stage tests continue to pass without regressions.

---

## 3. After Completing a Stage

### 3.1 Stop and Report
When all acceptance criteria of the current stage are met:
1. Run the full test suite: `pytest backend/tests/ -v`.
2. Report results transparently.
3. Classify work completed using standardized statuses:
   - **Implemented**: Fully written, tested, and verified.
   - **Partially Implemented**: Working but with known limitations.
   - **Planned**: Scoped for a future stage.
   - **Blocked**: Awaiting user clarification or external dependency.
4. Report all files created or modified.
5. Report any assumptions made.
6. **Stop execution immediately.** Do not begin the next stage until the user reviews and confirms.

---

## 4. Specific Application Rules

1. **Approval Gate is Inviolable**: No email may be sent without an approval record whose SHA-256 content hash matches the draft content exactly.
2. **Quota is Database-Backed**: Today's sent count must be queried from `outreach_events` in SQLite before every send.
3. **Catch-All Gate**: `catch-all` email addresses require explicit manual approval (`catch_all_approved = 1`) before drafting or sending.
4. **Single Address Per Thread**: Exactly one selected email address per outreach thread. Never send duplicates to multiple addresses of the same person.
5. **Audit Log is Append-Only**: Never execute UPDATE or DELETE on `audit_log`.
6. **SQLite Foreign Keys**: Always execute `PRAGMA foreign_keys = ON` on every SQLite connection.
7. **Contact Deduplication**: Primary match on normalized LinkedIn URL; secondary on normalized email; name+company matches flag for review (`duplicate_flag = 1`) rather than auto-merging.
8. **Contact Provenance**: Every email and phone number must store individual source metadata (`source`, `source_url`, `captured_at`).
