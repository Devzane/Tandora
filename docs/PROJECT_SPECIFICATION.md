# Project Specification — Tandora Lead Management & Outreach Application

## 1. Product Purpose

Tandora is a local-first, AI-powered lead management and personalized outreach application designed to help an individual professional find opportunities, organize contacts, and conduct high-quality, verified email outreach campaigns at scale.

The application serves two primary use cases:

- **Employment outreach**: Discovering relevant job opportunities, capturing company data and job descriptions, identifying hiring decision-makers (recruiters, founders, CTOs, engineering managers), organizing contact details, and generating personalized professional outreach emails.
- **Freelance client acquisition**: Identifying companies that may require cloud, DevOps, AI/ML, or automation services; capturing prospect company context and decision-makers; and generating personalized business development emails.

The application supports the complete outreach lifecycle:
$$\text{Capture Opportunity/Lead} \rightarrow \text{Capture Contacts/Provenance} \rightarrow \text{Verify Email} \rightarrow \text{Generate AI Draft} \rightarrow \text{Review \& Approve Hash} \rightarrow \text{Persistent Send Attempt} \rightarrow \text{Track Replies/Bounces} \rightarrow \text{Schedule Follow-ups}$$

---

## 2. Target Users and Use Cases

### Initial User
One person operating the application locally on a Windows 11 laptop (16 GB RAM, 512 GB SSD, \$0 software budget). No multi-user, multi-tenant, or commercial billing features are in scope.

### Primary Use Cases

| ID | Use Case | Description |
|----|----------|-------------|
| UC-01 | Capture LinkedIn Profile | Extract prospect name, headline, current company, title, location, and LinkedIn URL via Chrome Extension |
| UC-02 | Capture LinkedIn Post | Capture post author, post text excerpt, post URL, timestamp, and company context (distinct from profile owner) |
| UC-03 | Capture Third-Party Overlay (Conditional) | Conditionally read visible contact information from ContactOut or Apollo.io panels when open and accessible in active DOM |
| UC-04 | Essential Manual Fallback Capture | Mandatory paste-and-parse interface in extension popup with heuristic extraction when overlays are isolated or in closed shadow DOM |
| UC-05 | Web Opportunity Capture | Capture job postings and company leads from arbitrary websites or job boards |
| UC-06 | Manage Prospects via Local UI | View, create, edit, filter organizations, opportunities, contacts, emails, and phone numbers in a local web interface |
| UC-07 | Verify Emails via Reoon | Verify deliverability with 30-day caching, classifying safe, catch-all, invalid, unknown, role, and disposable |
| UC-08 | Catch-All Review & Approval | Flag catch-all emails for mandatory manual review and separate explicit approval before use |
| UC-09 | Generate AI Drafts | Generate personalized drafts via Gemini API (or optional Ollama) with context and versioning |
| UC-10 | Approve Draft & Record Content Hash | Review draft and compute immutable SHA-256 content hash covering recipient, subject, body, draft ID, and version |
| UC-11 | Execute Persistent Send Attempt | Dispatch email via Zoho SMTP using persistent lifecycle (`pending` $\rightarrow$ `sending` $\rightarrow$ `sent`/`failed`/`unknown`) |
| UC-12 | Dry-Run Simulation | Test complete outreach and queueing pipeline safely in dry-run mode without real email transmission |
| UC-13 | Monitor Inbox & Suppress | Poll Zoho IMAP for replies and bounces, linking threads and auto-suppressing pending follow-ups |
| UC-14 | Schedule & Recover Follow-ups | Database-driven follow-up scheduling (days 3, 7, 14) with automatic recovery on server restart |
| UC-15 | Synchronize Google Sheets | User-triggered bidirectional sync with conflict detection and idempotency |
| UC-16 | Global Pause & Quota Management | Globally halt outbound sending and enforce a hard limit of 20 emails/day |
| UC-17 | Multi-Level Suppression | Permanently suppress contacts, individual email addresses, or entire organizations |

---

## 3. Functional Requirements

### 3.1 Data Capture & Provenance
- **FR-01**: Support multiple organizations/companies, with multiple opportunities per organization.
- **FR-02**: Support multiple contacts per organization, and multiple contacts linked to an opportunity.
- **FR-03**: Support multiple contact roles per contact (e.g., Founder, CTO, Hiring Manager) without artificial limits.
- **FR-04**: Support multiple email addresses and phone numbers per contact, stored as independent records.
- **FR-05**: Every captured email address and phone number must preserve individual provenance: source (`ContactOut`, `Apollo`, `LinkedIn`, `manual`, `website`), source URL, and capture timestamp.
- **FR-06**: Capture distinct LinkedIn post context (`post_author`, `post_url`, `post_text`, `company_mentioned`) without incorrectly conflating post authors with personal profile owners.
- **FR-07**: Capture raw payloads in a dedicated `captures` entity for auditability and recovery.

### 3.2 Contact Deduplication
- **FR-08**: Deterministic primary deduplication using normalized LinkedIn URLs (strip tracking query params, trailing slashes, case-fold domain).
- **FR-09**: Secondary deduplication matching on normalized email addresses (trimmed whitespace, lowercased).
- **FR-10**: Name + Organization matches must be treated cautiously: flag as potential duplicate for manual review (`duplicate_flag = 1`) rather than auto-merging.
- **FR-11**: Never silently discard contact details during deduplication. Preserve distinct email and phone records.

### 3.3 Email Verification (Reoon)
- **FR-12**: Verify email addresses via the official Reoon Email Verifier API (`mode=power`).
- **FR-13**: Classify verification results: `safe`, `catch-all`, `invalid`, `unknown`, `role_account`, `disposable`.
- **FR-14**: Cache results for 30 days to avoid redundant API credit expenditure.
- **FR-15**: `safe` addresses are eligible for outreach.
- **FR-16**: `catch-all` addresses must be explicitly approved (`catch_all_approved = 1`) by the user before draft generation or sending.
- **FR-17**: `invalid`, `unknown`, and `disposable` addresses are permanently blocked from outreach.
- **FR-18**: Track and log Reoon API credit consumption.

### 3.4 AI Draft Generation
- **FR-19**: Generate personalized initial and follow-up drafts using the Gemini API (`gemini-1.5-flash`), with optional fallback to local Ollama (`llama3.2`).
- **FR-20**: Abstract LLM providers through a common interface; switchable via configuration without code modifications.
- **FR-21**: Every generation creates a new draft version. Historical versions remain immutable.
- **FR-22**: Prompt template injects organization, opportunity, contact background, notes, and post context.
- **FR-23**: Enforce strict structured output parsing and validation (no unfilled placeholders like `[COMPANY]`).

### 3.5 Approval Integrity & Content Hashing
- **FR-24**: No email (initial or follow-up) may ever be dispatched without an explicit, recorded approval.
- **FR-25**: Upon approval, calculate and store an immutable SHA-256 hash (`approved_content_hash`) over: `recipient_address + "\n" + subject + "\n" + body + "\n" + str(draft_id) + "\n" + str(version)`.
- **FR-26**: Immediately before sending, recalculate the hash from the current draft. Block dispatch if the hash differs.
- **FR-27**: Any manual edit to a draft creates a new version (`is_edited = 1`), automatically invalidating previous approvals and requiring fresh review.

### 3.6 Email Delivery Reliability & Persistent Send Lifecycle
- **FR-28**: Enforce a persistent send-attempt lifecycle with explicit states: `pending` $\rightarrow$ `sending` $\rightarrow$ `sent` / `failed` / `unknown`.
- **FR-29**: Pre-send checks must be validated and a `send_attempts` record committed to SQLite *before* contacting Zoho SMTP.
- **FR-30**: If SMTP accepts the message, update state to `sent` and record the returned `Message-ID`.
- **FR-31**: If SMTP definitively rejects the message, record state as `failed` with error details.
- **FR-32**: If connection drops mid-flight or status is indeterminate, record state as `unknown`. Do not automatically resend `unknown` attempts; require manual user reconciliation.
- **FR-33**: Generate a unique idempotency key per send attempt to guarantee duplicate sends cannot occur.
- **FR-34**: Serialize send operations in the service layer to prevent race conditions on quotas and concurrent dispatches.
- **FR-35**: Support a configuration toggle `dry_run = true` (default) that executes the complete pipeline and records lifecycle states without touching live SMTP.
- **FR-36**: Global sending quota: maximum 20 messages per calendar day (including initial outreach and follow-ups).
- **FR-37**: Global pause toggle: when enabled, halts all outbound sending immediately.

### 3.7 Inbox Monitoring & Suppression
- **FR-38**: Poll Zoho IMAP for unread inbound messages and Delivery Status Notifications (DSNs).
- **FR-39**: Match replies to threads using `In-Reply-To` and `References` headers matching sent `Message-ID`s.
- **FR-40**: Upon reply detection, update thread status to `replied` and automatically suppress all pending follow-ups.
- **FR-41**: Detect hard bounces, flag the address as suppressed, and record a bounce event.
- **FR-42**: Support multi-level suppression: person-level (`contacts.suppressed`), address-level (`email_addresses.suppressed`), and organization-level (`companies.suppressed`).
- **FR-43**: Cancelling/suppressing an entity immediately cancels all associated pending follow-up schedules.

### 3.8 Follow-up Scheduling & Database Recovery
- **FR-44**: Follow-ups are scheduled for day 3, day 7, and day 14 relative to initial send date.
- **FR-45**: SQLite is the authoritative source for scheduled work (`followup_schedules`). No reliance on in-memory timers.
- **FR-46**: Each follow-up draft is independently generated and requires separate user approval.
- **FR-47**: On application startup, scan SQLite for pending/overdue schedules, re-verify thread eligibility and pre-send rules, and resume safely without creating duplicate messages.

### 3.9 Minimal Functional Local Interface
- **FR-48**: Provide a lightweight local server-rendered UI (FastAPI + Jinja2 + HTML/CSS/JS) binding to `127.0.0.1:8000`.
- **FR-49**: Provide dedicated views for: Dashboard, Organizations, Opportunities, Contacts, Emails & Phones, Verifications, Outreach Threads, Draft Review & Approval, Sending Activity & Send Attempts, Suppression Management, and Google Sheets Sync.

### 3.10 Google Sheets Synchronization
- **FR-50**: User-triggered (manual) bidirectional sync with Google Sheets API v4.
- **FR-51**: Match records using stable `external_id`s. Detect conflicts when updated in both sources and surface to user for manual resolution. Idempotent execution.

### 3.11 Audit Logging
- **FR-52**: Append-only immutable `audit_log` table recording all lifecycle events (capture, verification, draft, approval, send attempt, delivery, reply, bounce, suppression, sync). No UPDATE or DELETE allowed.

---

## 4. Non-Functional Requirements

| ID | Requirement | Detail |
|----|-------------|--------|
| NFR-01 | Host Platform | Windows 11 laptop, 16 GB RAM, 512 GB SSD. |
| NFR-02 | Budget | \$0 initial software budget. Open-source or free-tier quotas only. |
| NFR-03 | Localhost Binding | API and UI bind strictly to `127.0.0.1:8000`. No external network exposure. |
| NFR-04 | Persistence | SQLite is the sole authoritative database. No data loss across process restarts. |
| NFR-05 | Secrets Management | All credentials loaded from `.env` via `python-dotenv`. Zero hardcoded secrets. |
| NFR-06 | Performance | Core API/UI operations respond in $< 500$ ms. LLM/Verification calls handle network timeouts gracefully. |
| NFR-07 | Resilience | Automatic recovery on startup for pending follow-ups and unconfirmed send attempts. |
| NFR-08 | Compliance | Full audit logging, opt-out suppression, and least-privilege extension architecture. |

---

## 5. Constraints

- **Database**: SQLite only via SQLAlchemy 2.x and Alembic. Supabase and PostgreSQL are strictly prohibited.
- **Email Delivery**: Zoho SMTP (port 587 STARTTLS) and IMAP (port 993 SSL). Dry-run mode by default.
- **Daily Limit**: 20 emails/day hard limit enforced at database level across all campaigns.
- **Approval Gate**: Mandatory SHA-256 hash validation before every outbound send.
- **Catch-All Gate**: Explicit manual approval required for catch-all emails.
- **Single Recipient**: Exactly one selected email address per outreach thread. No duplicate sends.
- **Extension**: Chrome Manifest V3, `activeTab`, `scripting`, `storage`, host permission `http://127.0.0.1:8000/*` only. No `<all_urls>`.
- **Third-Party Overlays**: Extraction from ContactOut or Apollo is strictly conditional and best-effort due to closed shadow roots and frame sandboxing. The manual copy-paste fallback parser is an essential, mandatory core capability.
- **Authoritative Concurrency Coordination**: SQLite transactional coordination (`BEGIN IMMEDIATE`) and database constraints are the authoritative safeguards for quotas, duplicate send prevention, and follow-up claims across multiple processes and restarts; in-memory locks are strictly auxiliary.

---

## 6. Initial Scope (Stages 0 to 9)

1. **Stage 0**: Project foundation (FastAPI, SQLite, Alembic, config, health test).
2. **Stage 1**: Core data management and local server-rendered UI (Organizations, Opportunities, Contacts, Roles, Emails, Phones, Deduplication, Dashboard & management views).
3. **Stage 2**: Chrome Extension (MV3, LinkedIn profile/post capture, ContactOut/Apollo visible capture, manual fallback, review popup, authenticated capture endpoint).
4. **Stage 3**: Email verification (Reoon client, 30-day cache, catch-all approval gate, credit tracking).
5. **Stage 4**: AI draft generation (Gemini provider, optional Ollama, prompt templates, versioning).
6. **Stage 5**: Approval and sending safeguards (Approval records, SHA-256 content hashes, 20/day quota, pause toggle, persistent send attempts, dry-run mode, audit log).
7. **Stage 6**: Zoho email delivery & inbox monitoring (SMTP client, IMAP poller, reply matching, bounce handling, delivery reconciliation).
8. **Stage 7**: Follow-up scheduler (Persistent database scheduling, startup recovery, days 3/7/14, auto-suppression on reply).
9. **Stage 8**: Google Sheets bidirectional synchronization (Manual trigger, conflict detection, idempotency).
10. **Stage 9**: Integration testing, hardening, and operational polish.

---

## 7. Deferred Features

| Feature | Reason Deferred |
|---------|-----------------|
| User registration & multi-tenant auth | Single-user local application |
| Multi-user role-based permissions | Unnecessary complexity for single operator |
| Commercial billing & payment processing | Non-commercial internal tool |
| Enterprise admin dashboard | Single-user local deployment |
| AWS / Cloud migration / Kubernetes | Local Windows 11 deployment meets all needs |
| Automated LinkedIn scraping / bot loops | Strict compliance with terms of service and safety |

---

## 8. Acceptance Criteria

- **AC-01 (Data Model & Deduplication)**: Organizations, opportunities, contacts, roles, emails, phones, captures, and posts can be managed with deterministic deduplication by normalized LinkedIn URL and normalized email.
- **AC-02 (Local UI)**: The user can view metrics, browse entities, review drafts, approve sends, and manage suppressions via a local web interface at `http://127.0.0.1:8000`.
- **AC-03 (Chrome Extension)**: Captures LinkedIn profiles, LinkedIn posts (preserving author distinction), and ContactOut/Apollo visible overlays with review popup and manual fallback under least-privilege permissions.
- **AC-04 (Provenance)**: Every email and phone number record stores its individual source, source URL, and timestamp.
- **AC-05 (Email Verification)**: Reoon verifies addresses with 30-day caching. Safe addresses are usable; catch-all addresses require manual approval; invalid addresses are blocked.
- **AC-06 (AI Drafting)**: Drafts generated with versioning using rich entity context. Provider switchable between Gemini and Ollama via config.
- **AC-07 (Approval Hash Integrity)**: Approvals record a SHA-256 content hash. Any draft modification invalidates approval. Sends blocked if hash mismatches.
- **AC-08 (Delivery Reliability)**: Persistent `send_attempts` lifecycle (`pending` $\rightarrow$ `sending` $\rightarrow$ `sent`/`failed`/`unknown`). Idempotency key prevents duplicate sends. No auto-resend on `unknown`. Dry-run mode supported.
- **AC-09 (Quota & Pause)**: Hard limit of 20 emails/day verified from database records. Global pause toggle immediately halts sending.
- **AC-10 (Inbox Monitoring)**: Zoho IMAP matches replies, updates thread to `replied`, and suppresses pending follow-ups. Bounces flag address suppression.
- **AC-11 (Scheduler Recovery)**: SQLite-driven scheduling survives application restarts, recovering overdue tasks safely without duplicate dispatches.
- **AC-12 (Google Sheets Sync)**: Bidirectional sync matches stable external IDs, detects conflicts, and runs idempotently.
- **AC-13 (Audit Trail)**: All critical events written to append-only `audit_log`.
