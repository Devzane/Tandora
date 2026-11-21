# Security and Compliance — Tandora Lead Management & Outreach Application

## 1. Secrets Management & Configuration Strategy

### 1.1 Strict Rules
- **No secrets in source code**: API keys, passwords, and tokens must never appear in Python files, JavaScript files, or any committed repository files.
- **No secrets in version control**: The `.env` file is explicitly ignored in `.gitignore`. It must never be committed.
- **Environment variables are authoritative**: All sensitive credentials are loaded via `python-dotenv` at runtime.

### 1.2 Required & Optional Environment Variables

| Variable | Purpose | Classification |
|----------|---------|----------------|
| `EXTENSION_API_SECRET` | Shared secret header (`X-Extension-Secret`) for Chrome Extension | Core Local Security |
| `DATABASE_PATH` | Path to SQLite database file (default: `./data/tandora.db`) | Local Storage |
| `DRY_RUN` | Enable simulated delivery mode without real SMTP dispatch (default: `true`) | Delivery Safeguard |
| `GEMINI_API_KEY` | Gemini API key for AI draft generation | Integration |
| `REOON_API_KEY` | Reoon Email Verifier API key | Integration |
| `ZOHO_SMTP_USERNAME` | Zoho Mail sender email address | Integration |
| `ZOHO_SMTP_PASSWORD` | Zoho Mail application-specific password | Integration |
| `ZOHO_IMAP_USERNAME` | Zoho Mail inbox monitoring address | Integration |
| `ZOHO_IMAP_PASSWORD` | Zoho Mail IMAP application-specific password | Integration |
| `GOOGLE_CREDENTIALS_PATH` | Path to Google Cloud Service Account credentials JSON | Integration |
| `GOOGLE_SHEETS_ID` | Target spreadsheet ID for bidirectional sync | Integration |
| `OLLAMA_BASE_URL` | Base URL for local Ollama instance (default: `http://127.0.0.1:11434`) | Integration |

### 1.3 Integration-Specific On-Demand Validation
The application boots cleanly without requiring all external service credentials upfront. 

- Unconfigured integrations do not block unrelated features or application startup.
- When an operation requires an unconfigured service (e.g., verifying an address without `REOON_API_KEY`), the service raises a clear, actionable error identifying the missing variable.
- Secrets are never exposed in logs, error traces, or API responses.

---

## 2. API & Network Security

### 2.1 Localhost Binding
- The FastAPI application binds strictly to `127.0.0.1:8000`.
- Binding to `0.0.0.0` or public interfaces is strictly prohibited.
- No remote access, tunneling, or public port forwarding is configured.

### 2.2 Chrome Extension Authentication
- Every request from the Chrome Extension to `/api/v1/captures` must include the `X-Extension-Secret` header.
- The extension stores this secret securely in `chrome.storage.local`.
- The backend validates the secret via dependency injection (`require_extension_secret`). Missing or incorrect secrets return HTTP 401.

---

## 3. Database Security & Integrity

### 3.1 SQL Injection Prevention
- All database interactions use SQLAlchemy 2.x parameterized statements (`select()`, `insert()`).
- Raw SQL string concatenation is strictly prohibited.
- `PRAGMA foreign_keys = ON` is enforced on every SQLite connection.

### 3.2 Audit Log Immutability
- The `audit_log` table is strictly append-only (INSERT-only).
- No code path or API endpoint may execute `UPDATE` or `DELETE` on `audit_log`.

---

## 4. Approval Integrity & Content Hashing

### 4.1 SHA-256 Approval Content Hash
To guarantee that the exact text approved by the user is what gets transmitted, Tandora enforces cryptographic content hashing:

$$\text{approved\_content\_hash} = \text{SHA256}(\text{recipient\_address} + \text{"\textbackslash n"} + \text{subject} + \text{"\textbackslash n"} + \text{body} + \text{"\textbackslash n"} + \text{str(draft\_id)} + \text{"\textbackslash n"} + \text{str(version)})$$

### 4.2 Pre-Send Hash Validation
Immediately before dispatching an email:
1. The delivery service recalculates the SHA-256 hash from the current draft content and selected recipient.
2. It compares this value against `approvals.approved_content_hash`.
3. If the hashes differ, sending is immediately aborted and flagged as an approval integrity failure.

### 4.3 Invalidation on Edit
Any manual edit or regeneration of a draft automatically creates a new draft version (`is_edited = 1`, `version = N+1`). The approval record for the prior version is invalid for the new version, requiring explicit re-approval.

---

## 5. Email Delivery Reliability & Persistent Send Attempts

### 5.1 Distributed Transaction Limitation
SMTP and SQLite do not participate in a shared, two-phase distributed transaction. If the application crashes or network drops after SMTP accepts an email but before SQLite commits, a duplicate-delivery risk exists.

To address this limitation, Tandora implements a multi-step persistent lifecycle state machine:
$$\text{Pre-Send Checks} \rightarrow \text{Persist 'pending' Attempt} \rightarrow \text{Commit DB} \rightarrow \text{Transition 'sending'} \rightarrow \text{Dispatch SMTP} \rightarrow \text{Commit 'sent'/'failed'/'unknown'}$$

### 5.2 Send Attempt Lifecycle States

| State | Definition | Next Action |
|-------|------------|-------------|
| `pending` | Pre-send checks passed; unique send-attempt committed to DB | Proceed to open SMTP socket |
| `sending` | Socket opened; message transmitted to SMTP relay | Await SMTP 250 response |
| `sent` | SMTP server confirmed receipt (`250 OK`); Message-ID recorded | Record `outreach_event`; schedule follow-ups |
| `failed` | SMTP relay definitively rejected message (e.g. 5xx error) | Log error; quota not incremented; no resend |
| `unknown` | Socket timed out or dropped mid-flight; delivery indeterminate | **NEVER auto-resend**; flag for manual user reconciliation |

### 5.3 Idempotency & Concurrency Coordination
- **Authoritative Database Constraints**: Enforced by a database-level `UNIQUE` constraint on `send_attempts.idempotency_key` (`SHA256(thread_id + "_" + draft_id + "_" + approval_id + "_" + attempt_number)`). Duplicate requests are aborted at the database layer with `IntegrityError`.
- **Authoritative Transactional Coordination**: Quota checks, send-attempt creation, and follow-up claims occur inside SQLite `BEGIN IMMEDIATE` transactions. This provides persistent protection across multiple processes, workers, and application restarts.
- **Auxiliary In-Process Lock**: An in-memory `threading.Lock` operates in Python as a secondary optimization to minimize SQLite lock contention in a single process, but database constraints and transactions remain the authoritative safeguard.

### 5.4 Dry-Run Mode
- Controlled by `DRY_RUN = true` (default in development and testing).
- Simulates complete pre-send checks, approval hash verification, send-attempt state transitions, and follow-up scheduling without establishing external SMTP connections.
- Requires explicit user configuration to switch to live sending.

---

## 6. Safe Sending Controls (10 Mandatory Pre-Send Checks)

Every outbound email dispatch must satisfy all 10 checks against persistent database records:

1. ✅ **Exact Version Approval**: Valid `approvals` record exists referencing the exact current `draft_id`.
2. ✅ **Global Pause Disabled**: `app_config.sending_paused == 'false'`.
3. ✅ **Daily Quota Available**: Today's sent count from `outreach_events` $< 20$ messages globally.
4. ✅ **Contact Not Suppressed**: `contacts.suppressed == 0`.
5. ✅ **Address Not Suppressed**: `email_addresses.suppressed == 0` and no hard bounce in `bounces`.
6. ✅ **Verification Eligibility**: Selected email address status is `safe` or approved `catch-all`.
7. ✅ **Catch-All Approval**: Explicit manual approval granted (`catch_all_approved == 1`) if status is `catch-all`.
8. ✅ **No Duplicate Recipient**: No existing `outreach_events` record for this thread and event/followup type.
9. ✅ **Thread Eligibility**: `outreach_threads.status` is active and not `suppressed`, `replied`, `bounced`, or `closed`.
10. ✅ **Content Integrity**: Draft content SHA-256 hash matches `approvals.approved_content_hash`.

If any check fails, dispatch is aborted, a `send_blocked` entry is recorded in `audit_log`, and the daily quota is not incremented.

---

## 7. Privacy, Third-Party Compliance & Outreach Regulations

### 7.1 Third-Party Extension Boundaries (ContactOut & Apollo)
- **Zero API Scraping**: Tandora never interacts with, reverse-engineers, or calls ContactOut or Apollo backend servers.
- **Strictly Conditional DOM Extraction**: Reading visible overlays from ContactOut or Apollo.io is strictly best-effort and conditional. Closed shadow roots, isolated extension contexts, and sandboxed iframes inherently prevent content scripts from inspecting or traversing third-party extension UI elements.
- **Essential Manual Paste Fallback**: Because DOM access cannot be guaranteed, the manual copy-paste fallback parser is a mandatory, first-class requirement. The popup provides a direct paste-and-parse interface with heuristic regex extraction so the user can paste contact text directly.
- **User Initiation**: Data is extracted only upon explicit user action (clicking Capture or pressing `Alt+Shift+T`). No background DOM scraping.

### 7.2 LinkedIn Terms Compliance
- No automated profile-discovery loops, scraping bots, or background crawling.
- Captures are strictly user-initiated from pages the user has manually navigated to.
- Preserves post author identity as distinct from profile owners.

### 7.3 Email Verification is Not Consent
- Reoon verification confirms deliverability only. It does not imply consent.
- Outreach messages must include a clear, natural-language opt-out statement.

### 7.4 Multi-Level Suppression
- **Contact-Level**: `contacts.suppressed = 1`. Permanently blocks outreach to that individual across all opportunities.
- **Address-Level**: `email_addresses.suppressed = 1`. Blocks outreach using that specific email address.
- **Organization-Level**: `companies.suppressed = 1`. Blocks outreach to any contact employed by that organization.
- **Auto-Cancellation**: Suppressing an entity immediately cancels all associated pending `followup_schedules`.

### 7.5 SPF, DKIM & DMARC Deliverability Requirements
Before switching `DRY_RUN = false` for live Zoho sending, the user must ensure their custom domain is configured with:
- **SPF**: Valid TXT record including `v=spf1 include:zoho.com ~all`.
- **DKIM**: Valid domain key TXT record configured in Zoho Mail admin.
- **DMARC**: Policy TXT record (e.g. `v=DMARC1; p=none; ...`) to protect domain reputation.
- The 20-message daily limit is Tandora's internal safety cap to protect domain warm-up and account standing.

---

## 8. Failure Handling & Recovery

| Failure Mode | Detection | System Action |
|--------------|-----------|---------------|
| SMTP 5xx Permanent Failure | SMTP response code | Mark send attempt `failed`; log error; do not increment quota; do not retry automatically |
| SMTP Connection Timeout | Socket timeout exception | Mark send attempt `unknown`; flag in UI for manual review; never auto-resend |
| IMAP Connection Failure | Poller connection exception | Log error in audit log; retry on next 15-minute polling cycle |
| Reoon API Downtime | HTTP 5xx or connection error | Abort verification; return actionable error; address remains unverified |
| LLM API Outage | Gemini/Ollama HTTP error | Abort draft generation; return error to user; no draft version created |
| Application Restart Mid-Queue | Startup recovery routine | Scans SQLite for overdue follow-ups, re-verifies 10 pre-send checks, resumes safely |
