# Main Application Implementation Prompt — Tandora

## Instructions for the Implementing Agent

You are a senior software engineer implementing the Tandora lead management and personalized outreach application. This is a local-first, single-user application running on Windows 11. You must adhere strictly to all project specifications, architectural decisions, and operational constraints defined in this project before writing any code.

---

## Step 1: Workspace & Documentation Discovery

The project root is the currently opened workspace directory (`<workspace_root>`). Do not assume any specific absolute path, Windows username, or fixed host directory.

Before writing code for any stage, discover and read the complete documentation in `docs/` relative to the workspace root in this exact sequence:

1. `docs/PROJECT_SPECIFICATION.md` — Core requirements, scope, and acceptance criteria.
2. `docs/ARCHITECTURE.md` — Component architecture, local web UI design, and data flows.
3. `docs/DATABASE_SCHEMA.md` — Authoritative 21-table schema, deduplication rules, and data integrity constraints.
4. `docs/WORKFLOWS.md` — 12 end-to-end user and system workflows.
5. `docs/SECURITY_AND_COMPLIANCE.md` — Security, SHA-256 approval hashing, send attempts, and compliance.
6. `docs/IMPLEMENTATION_ROADMAP.md` — 10 practical implementation stages (Stages 0 to 9).
7. `docs/AGENT_INSTRUCTIONS.md` — Mandatory coding agent rules and operational constraints.

---

## Step 2: Identify the Current Implementation Stage

Consult `docs/IMPLEMENTATION_ROADMAP.md`. Inspect the current repository state:
- Check existing directories and code in `backend/` and `extension/`.
- Check applied Alembic migrations in `backend/alembic/versions/`.
- Check existing automated test suites in `backend/tests/`.

Determine:
1. Which stages are already complete (all code and passing tests present).
2. Which stage is next in sequence (Stages 0 to 9).
3. The exact objective, dependencies, features, expected files, tests, and acceptance criteria for that stage.

**Never jump ahead. Never implement features across multiple stages in a single turn.**

---

## Step 3: Load Relevant Project Skills

Project-level AI coding skills are stored as instruction files in `skills/` relative to the workspace root. They are project documentation assets, not globally installed runtime extensions.

Before implementing a stage, read the corresponding skill files:

| Component / Task | Project Skill File |
|------------------|--------------------|
| Python backend architecture & coding standards | `skills/python-backend/SKILL.md` |
| FastAPI routers, Jinja2 templates, dependencies & testing | `skills/fastapi-development/SKILL.md` |
| SQLite, SQLAlchemy 2.x, Alembic & transactions | `skills/sqlite-database/SKILL.md` |
| Chrome Extension Manifest V3 & DOM capture | `skills/chrome-extension/SKILL.md` |
| Google Sheets API v4 bidirectional sync & conflicts | `skills/google-sheets-integration/SKILL.md` |
| Reoon API email verification & catch-all gating | `skills/email-verification/SKILL.md` |
| LLM provider abstraction (Gemini & Ollama) & drafting | `skills/llm-integration/SKILL.md` |
| Zoho SMTP sending, IMAP monitoring & rate limits | `skills/email-delivery/SKILL.md` |
| Pytest test suites, mocking & quality assurance | `skills/testing-and-quality/SKILL.md` |
| Security engineering, suppression & audit controls | `skills/security-engineering/SKILL.md` |
| Git version control, atomic commits & branch hygiene | `skills/git-workflow/SKILL.md` |

---

## Step 4: Implement the Current Stage

Implement strictly the scoped stage. Follow these core architectural standards:

### 1. Technology Stack Constraints
- Python 3.12+, FastAPI, SQLite, SQLAlchemy 2.x, Alembic, APScheduler, and Chrome Extension Manifest V3 (vanilla JS).
- Server-rendered local web UI using Jinja2 templates.
- Bind exclusively to `127.0.0.1:8000`.
- Do not introduce Supabase, PostgreSQL, Docker, Redis, Celery, Kubernetes, or cloud hosting.

### 2. Database Schema Authority (21 Tables)
`docs/DATABASE_SCHEMA.md` is the authoritative source for all database structures. All model definitions and code must match these exact names:
`companies`, `opportunities`, `contacts`, `contact_roles`, `email_addresses`, `phone_numbers`, `email_verifications`, `captures`, `linkedin_posts`, `opportunity_contacts`, `outreach_threads`, `drafts`, `approvals`, `send_attempts`, `outreach_events`, `followup_schedules`, `replies`, `bounces`, `sheets_sync_state`, `audit_log`, `app_config`.

- **Audit Log**: Strictly singular `audit_log`. Append-only (no UPDATE or DELETE allowed).
- **Suppression Handling**: Stored directly on entities (`contacts.suppressed`, `email_addresses.suppressed`, `companies.suppressed`) and logged in `audit_log`. No separate `suppression_list` table.
- **SQLite Pragmas**: Always execute `PRAGMA foreign_keys = ON;` and `PRAGMA journal_mode = WAL;`.

### 3. Contact Deduplication Standards
- **Primary Match**: Normalized LinkedIn URL (strip tracking params and trailing slashes; lowercase domain).
- **Secondary Match**: Normalized email address (lowercase, trimmed).
- **Cautious Matching**: First name + Last name + Company match without matching LinkedIn URL must be flagged for manual review (`duplicate_flag = 1`) rather than auto-merged.
- **Channel Provenance**: Every email and phone number is stored as an independent record preserving `source` (`ContactOut`, `Apollo`, `LinkedIn`, `manual`, `website`), `source_url`, and `captured_at`.

### 4. Chrome Extension Capture Scope
- Supported page types: LinkedIn individual profiles, LinkedIn posts, LinkedIn company pages, job listings, and prospect websites.
- **Post Author Separation**: Preserves post author as a potential decision-maker distinct from personal profile owners.
- **ContactOut & Apollo Integration (Conditional)**: Extraction from visible overlays is strictly best-effort and conditional; closed shadow roots, isolated extension contexts, and sandboxed frames can prevent DOM access. The manual paste-and-parse fallback form is therefore an essential, mandatory requirement.
- **Least-Privilege Security**: Permissions restricted to `activeTab`, `scripting`, `storage`, and host permission `http://127.0.0.1:8000/*` only. No `<all_urls>`.
- **Review Before Submit**: All extracted data displayed in editable popup form before submission.

### 5. Approval Content Integrity (SHA-256)
- Approvals must calculate and store a SHA-256 hash:
  $$\text{approved\_content\_hash} = \text{SHA256}(\text{recipient\_address} + \text{"\textbackslash n"} + \text{subject} + \text{"\textbackslash n"} + \text{body} + \text{"\textbackslash n"} + \text{str(draft\_id)} + \text{"\textbackslash n"} + \text{str(version)})$$
- Immediately before delivery, recalculate the hash from the current draft and verify an exact match.
- Any draft edit creates a new version (`is_edited = 1`), automatically invalidating previous approvals.

### 6. Email Delivery Reliability & Persistent Send Attempts
- Outbound delivery follows the persistent state machine: `pending` $\rightarrow$ `sending` $\rightarrow$ `sent` / `failed` / `unknown`.
- Persist `send_attempts` record and commit database transaction *before* opening SMTP socket.
- Never auto-resend an `unknown` attempt; require manual user reconciliation.
- Enforce unique idempotency keys per thread action via a database-level `UNIQUE` constraint on `send_attempts.idempotency_key`.
- Authoritative Concurrency Coordination: Quota enforcement (max 20 messages/day globally), duplicate send prevention, and concurrent follow-up execution are authoritatively governed by SQLite `BEGIN IMMEDIATE` transactions and database constraints across processes and restarts; in-memory locks serve strictly as an auxiliary process-level optimization.
- Default to `DRY_RUN = true` until live sending is explicitly configured.

### 7. 10 Mandatory Pre-Send Checks
Before every outbound email dispatch, verify all 10 checks against persistent database records:
1. Exact version approval exists in `approvals`.
2. Global pause toggle is disabled (`sending_paused == 'false'`).
3. Daily quota available ($< 20$ sent today).
4. Contact is not suppressed (`contacts.suppressed == 0`).
5. Selected address is not suppressed (`email_addresses.suppressed == 0` and no hard bounce in `bounces`).
6. Email verification status is eligible (`safe` or approved `catch-all`).
7. Catch-all address has separate explicit approval (`catch_all_approved == 1`).
8. Recipient has not already been sent an identical outreach message.
9. Outreach thread is eligible (not `suppressed`, `replied`, `bounced`, or `closed`).
10. Draft content SHA-256 hash matches `approvals.approved_content_hash`.

### 8. Database-Driven Scheduler Recovery
- Follow-up schedules (days 3, 7, 14) are stored authoritatively in SQLite (`followup_schedules`).
- On application startup, scan SQLite for pending or overdue tasks, re-verify thread eligibility and pre-send rules, and resume safely without creating duplicate messages.

### 9. Credential Management & On-Demand Validation
- Load configuration from environment variables via `python-dotenv`.
- Unconfigured integrations must not crash application startup.
- Validate integration credentials lazily on-demand when invoked.
- Maintain `.env.example` documenting all required variable names without real values.

### 10. Code Quality & Automated Testing
- Complete type hints on every Python function.
- Pydantic models for all API request/response schemas.
- Use Python's standard `logging` module. No `print()` calls in production code.
- Write unit, API, and integration tests in the same stage as the feature.
- Mock all external services (Reoon, Gemini, Ollama, Zoho SMTP/IMAP, Google Sheets). Never make real API calls or outbound emails in automated tests.

---

## Step 5: Complete Stage and Pause for Review

When all tasks and acceptance criteria of the current stage are met:

1. Run the full test suite: `pytest backend/tests/ -v`.
2. Confirm all tests pass.
3. Prepare a concise completion report detailing:
   - **Implemented**: Fully written, tested, and verified features.
   - **Partially Implemented**: Features with known limitations.
   - **Planned**: Features scoped for future stages.
   - **Blocked**: Items awaiting user input.
   - Files created or modified.
   - Tests executed and coverage summary.
   - Any assumptions made.
4. **Stop execution completely.** Do not proceed to the next stage until the user reviews and confirms.

---

## Reference Summary

All project documentation is located in `docs/` relative to the workspace root:
- `docs/PROJECT_SPECIFICATION.md` — Product scope, use cases, requirements.
- `docs/ARCHITECTURE.md` — Architecture, local web UI, component diagrams.
- `docs/DATABASE_SCHEMA.md` — Authoritative 21-table schema, integrity rules.
- `docs/WORKFLOWS.md` — 12 end-to-end user workflows.
- `docs/SECURITY_AND_COMPLIANCE.md` — Security, suppression, 10-point send checklist.
- `docs/IMPLEMENTATION_ROADMAP.md` — 10-stage phased plan (Stages 0 to 9).
- `docs/AGENT_INSTRUCTIONS.md` — Mandatory coding agent guidelines.

All 11 project skill guides are located in `skills/` relative to the workspace root.
