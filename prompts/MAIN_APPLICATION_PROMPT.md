# Main Application Implementation Prompt — Tandora

## Instructions for the Implementing Agent

You are a senior software engineer implementing the Tandora lead management and outreach application. This is a local, single-user application running on Windows 11. You must follow all documentation and rules defined in this project before writing any code.

---

## Step 1: Workspace & Documentation Discovery

The project root is the currently opened workspace directory (`<workspace_root>`). Do not assume any specific absolute path, Windows username, or fixed host directory.

Before writing any code, discover and read the project documentation located in the `docs/` directory relative to the workspace root, in this exact order:

1. `docs/PROJECT_SPECIFICATION.md` — Understand functional/non-functional requirements, constraints, and scope.
2. `docs/ARCHITECTURE.md` — Understand system architecture, components, and interactions.
3. `docs/DATABASE_SCHEMA.md` — Understand the authoritative 17-table SQLite schema and data integrity rules.
4. `docs/WORKFLOWS.md` — Understand the 12 operational user workflows.
5. `docs/SECURITY_AND_COMPLIANCE.md` — Understand security standards, suppression rules, and audit logging.
6. `docs/IMPLEMENTATION_ROADMAP.md` — Identify milestones, dependencies, and definitions of done.
7. `docs/AGENT_INSTRUCTIONS.md` — Understand mandatory coding agent rules and operational constraints.

Do not skip any document. They contain critical decisions that govern all implementation phases.

---

## Step 2: Identify the Current Milestone

Consult `docs/IMPLEMENTATION_ROADMAP.md`. Inspect the current repository state:
- Check existing directories and code in `backend/`.
- Check existing Alembic migrations in `backend/alembic/versions/`.
- Check existing test files in `backend/tests/`.
- Check existing extension files in `extension/`.

Determine:
1. Which milestones are already complete (all code and passing tests present).
2. Which milestone is next in sequence.
3. What the current milestone's objective, dependencies, features, expected files, tests, and acceptance criteria are.

**Never jump ahead. Never implement features across multiple milestones in a single turn.**

---

## Step 3: Load Relevant Project Skills

Project-level AI coding skills are stored as instruction files in the `skills/` directory relative to the workspace root. They are project documentation assets, not globally installed runtime extensions.

Before implementing a milestone, read the corresponding skill files:

| Component / Task | Project Skill File |
|------------------|--------------------|
| Python backend architecture & coding standards | `skills/python-backend/SKILL.md` |
| FastAPI routers, schemas, dependencies & API testing | `skills/fastapi-development/SKILL.md` |
| SQLite, SQLAlchemy 2.x, Alembic & transactions | `skills/sqlite-database/SKILL.md` |
| Chrome Extension Manifest V3 & local capture | `skills/chrome-extension/SKILL.md` |
| Google Sheets API v4 bidirectional sync & conflicts | `skills/google-sheets-integration/SKILL.md` |
| Reoon API email verification & catch-all gating | `skills/email-verification/SKILL.md` |
| LLM provider abstraction (Gemini & Ollama) & drafting | `skills/llm-integration/SKILL.md` |
| Zoho SMTP sending, IMAP monitoring & rate limits | `skills/email-delivery/SKILL.md` |
| Pytest test suites, mocking & quality assurance | `skills/testing-and-quality/SKILL.md` |
| Security engineering, suppression & audit controls | `skills/security-engineering/SKILL.md` |
| Git version control, atomic commits & branch hygiene | `skills/git-workflow/SKILL.md` |

---

## Step 4: Implement the Current Milestone

Implement strictly the scoped milestone. Follow these non-negotiable rules:

### Architecture Rules
- Use Python 3.12+, FastAPI, SQLite, SQLAlchemy 2.x, Alembic, and APScheduler.
- Use Chrome Extension Manifest V3 with vanilla JavaScript.
- Maintain a local, single-user Windows 11 footprint.
- Do not introduce Supabase, PostgreSQL, Docker, Redis, Celery, or cloud infrastructure.
- The FastAPI application must bind exclusively to `127.0.0.1` (localhost only).

### Database Naming & Schema Standards
`docs/DATABASE_SCHEMA.md` is the authoritative source for all database structures. All entities and code must match the canonical schema names exactly:
- `companies`
- `opportunities`
- `contacts`
- `contact_roles`
- `email_addresses`
- `email_verifications`
- `opportunity_contacts`
- `outreach_threads`
- `drafts`
- `approvals`
- `outreach_events`
- `followup_schedules`
- `replies`
- `bounces`
- `sheets_sync_state`
- `audit_log` (Note: Singular `audit_log`, never `audit_logs`. The table is strictly append-only; no UPDATE or DELETE operations permitted.)
- `app_config`

**Suppression Handling Standard**:
There is no separate `suppression_list` table. Suppression is tracked via:
1. `contacts.suppressed`, `contacts.suppressed_reason`, and `contacts.suppressed_at`.
2. `outreach_threads.status = 'suppressed'`.
3. Bounce records in `bounces` and invalid/unknown statuses in `email_verifications`.
4. Any suppression event is permanently recorded in `audit_log`.

### Credential & Configuration Management Strategy
- All sensitive credentials (API keys, passwords, tokens, secrets) must be loaded from environment variables using `python-dotenv`.
- Never hard-code credentials in source code or committed artifacts.
- Never expose secrets in application logs, error traces, or API responses.
- Maintain `.env.example` documenting all required environment variable names without real values.
- **Integration-Specific On-Demand Validation**:
  - The application must start successfully even if external API credentials (such as Reoon, Gemini, or Zoho) are not yet configured.
  - Each external integration must validate its specific credentials lazily when activated or when an operation requires it.
  - An unconfigured integration must raise a clear, actionable error identifying the missing environment variable and explaining how to configure it.
  - Unconfigured integrations must never prevent unrelated application functionality (e.g., a missing `REOON_API_KEY` must not block capturing opportunities, browsing companies, or running database migrations).

### Pre-Send Safety Validation (10 Mandatory Checks)
Every outbound email dispatch must pass through a centralized guard enforcing all 10 checks using persistent database records (never relying exclusively on in-memory state):

1. **Exact Version Approval**: A valid `approvals` record exists referencing the exact current `draft_id` (`approvals.draft_id == draft.id`).
2. **Global Pause Disabled**: The global pause setting in `app_config` is disabled (`sending_paused == 'false'`).
3. **Daily Quota Available**: The global daily sending limit in `app_config` (maximum 20 messages globally) has not been exceeded, verified by counting today's persistent records in `outreach_events`.
4. **Contact Not Suppressed**: The recipient contact is active (`contacts.suppressed == 0`).
5. **Address Not Suppressed**: The selected email address is not suppressed (no associated hard bounce record in `bounces`).
6. **Verification Eligibility**: The email address has a valid verification record in `email_verifications` with an eligible status (`safe` or approved `catch-all`).
7. **Catch-All Approval**: If the address verification status is `catch-all`, it has a separate, explicit manual approval (`catch_all_approved == 1`).
8. **No Duplicate Recipient**: The recipient has not already been sent an identical outreach message (no existing `outreach_events` record for the same thread and event/followup type).
9. **Thread Eligibility**: The parent outreach thread is active and eligible (`outreach_threads.status` is not `suppressed`, `replied`, `bounced`, or `closed`).
10. **Content Integrity**: The draft content (subject and body) has not been altered or tampered with since the approval was recorded.

If any check fails:
- Block outbound sending immediately.
- Record the blocking event and specific reason in `audit_log`.
- Do not increment the daily sending quota.

### Code Quality & Testing Rules
- Every Python function must have complete type hints.
- Use Pydantic schemas for all API request and response models.
- Use Python's standard `logging` module. No `print()` calls in production code.
- Write unit, API, and integration tests in the same milestone as the feature.
- Mock all external third-party services (Reoon, Gemini, Ollama, Zoho SMTP/IMAP, Google Sheets) during automated testing. Never trigger real API calls or outbound emails in automated tests.
- Verify that previous milestone tests continue to pass without regressions.

---

## Step 5: Complete Milestone and Pause for Review

When all tasks and acceptance criteria of the current milestone are completed:

1. Run the full test suite: `pytest backend/tests/ -v`.
2. Confirm all tests pass.
3. Prepare a concise completion report detailing:
   - Specific features and modules implemented.
   - Files created or modified.
   - Tests executed and coverage summary.
   - Any assumptions made or decisions requiring user attention.
4. **Stop execution completely.** Do not proceed to the next milestone until the user reviews and confirms.

---

## Reference Summary

All project documentation is located in `docs/` relative to the workspace root:
- `docs/PROJECT_SPECIFICATION.md` — Product scope, use cases, requirements.
- `docs/ARCHITECTURE.md` — Technical architecture, components, data flows.
- `docs/DATABASE_SCHEMA.md` — Authoritative 17-table schema, integrity rules.
- `docs/WORKFLOWS.md` — 12 end-to-end user workflows.
- `docs/SECURITY_AND_COMPLIANCE.md` — Security, suppression, 10-point send checklist.
- `docs/IMPLEMENTATION_ROADMAP.md` — 12-milestone phased plan (M0–M11).
- `docs/AGENT_INSTRUCTIONS.md` — Mandatory coding agent guidelines.

All project skill guides are located in `skills/` relative to the workspace root.
