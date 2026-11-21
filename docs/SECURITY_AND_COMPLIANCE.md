# Security and Compliance — Tandora Lead Management & Outreach Application

## 1. Secrets Management

### 1.1 Rules

- **No secrets in source code.** API keys, passwords, and tokens must never appear in Python files, JavaScript files, or any file that could be committed to version control.
- **No secrets in version control.** The `.env` file must be listed in `.gitignore`. It must never be committed.
- **Environment variables are the authority.** All sensitive configuration is loaded from environment variables at application startup.

### 1.2 Required Environment Variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Gemini API authentication |
| `REOON_API_KEY` | Reoon Email Verifier API key |
| `ZOHO_SMTP_USERNAME` | Zoho SMTP login (email address) |
| `ZOHO_SMTP_PASSWORD` | Zoho SMTP app password |
| `ZOHO_IMAP_USERNAME` | Zoho IMAP login (email address) |
| `ZOHO_IMAP_PASSWORD` | Zoho IMAP app password |
| `GOOGLE_CREDENTIALS_PATH` | Path to Google API credentials JSON file |
| `GOOGLE_SHEETS_ID` | Target spreadsheet ID |
| `EXTENSION_API_SECRET` | Shared secret for Chrome Extension authentication |
| `DATABASE_PATH` | Path to SQLite database file |
| `OLLAMA_BASE_URL` | Ollama local server URL (optional) |

### 1.3 `.env` File Template

A `.env.example` file (containing no real values, only key names) must be committed to the repository. The actual `.env` file must never be committed.

### 1.4 Credential Loading & Validation Strategy

The backend loads configuration from environment variables via `python-dotenv`. To ensure modularity and operational reliability, the application must start without requiring all external API credentials to be present upfront.

Each external integration validates its specific credentials when activated or when an operation requires them (on-demand validation):
- If an operation is invoked without required credentials (e.g. attempting Reoon verification without `REOON_API_KEY`, or sending via Zoho without `ZOHO_SMTP_PASSWORD`), the system returns a clear, actionable error message naming the missing environment variable.
- Unconfigured integrations must never block unrelated application functionality (e.g., missing verification or LLM keys must not prevent capturing leads, browsing companies, or running database migrations).
- Credentials must never be hard-coded in source files or exposed in logs and API responses.

---

## 2. API Authentication

### 2.1 Chrome Extension Authentication

The Chrome Extension communicates with the FastAPI backend over `localhost`. To prevent unauthorized requests from other local processes:

- A shared secret (`EXTENSION_API_SECRET`) is configured in both the extension's storage and the backend's `.env`.
- The extension includes this secret as an HTTP header (`X-Extension-Secret`) on every request.
- The backend validates this header on all endpoints used by the extension.
- This secret is not a user-facing credential. It is set once during installation and never changed in normal operation.

> **Note**: This is a minimal local authentication mechanism. It is not equivalent to full user authentication. Its purpose is to prevent other local processes from accidentally or maliciously posting data to the backend.

### 2.2 Backend API Access

In the initial single-user local deployment:
- The FastAPI backend binds to `127.0.0.1` only. It must not bind to `0.0.0.0`.
- No public-facing API is exposed.
- No TLS is required for localhost communication.

If the deployment ever changes to allow network access, TLS and proper authentication must be added before that change.

### 2.3 Google Sheets API Authentication

Authentication uses a Google service account credentials JSON file, the path to which is provided via `GOOGLE_CREDENTIALS_PATH`. This file must:
- Be stored outside the repository directory.
- Have read permissions restricted to the current user only.
- Be backed up securely.

---

## 3. Database Security

### 3.1 SQLite File Security

- The database file must be stored in a location accessible only to the current user.
- File system permissions must restrict access to the application user.
- The database file path is configured via `DATABASE_PATH` in the `.env` file.

### 3.2 SQL Injection Prevention

- All database queries must use SQLAlchemy's parameterized query mechanisms.
- Raw SQL string formatting with user-supplied data is prohibited.
- ORM methods and SQLAlchemy Core with bound parameters are the only acceptable query patterns.

### 3.3 Audit Log Immutability

- The `audit_log` table must never have UPDATE or DELETE operations performed on it by the application.
- The application must not expose any API endpoint that modifies or deletes audit log entries.
- Database-level constraints (triggers or application-level enforcement) should prevent deletion.

---

## 4. Email Security

### 4.1 SMTP Authentication

- Zoho SMTP uses TLS (port 587 with STARTTLS or port 465 with SSL).
- Authentication uses an app-specific password stored in `ZOHO_SMTP_PASSWORD`.
- The main account password must not be used. App passwords are preferred for security isolation.

### 4.2 IMAP Authentication

- Zoho IMAP uses TLS (port 993).
- Authentication uses an app-specific password stored in `ZOHO_IMAP_PASSWORD`.

### 4.3 Message-ID Tracking

- Every outbound email must have a unique `Message-ID` header set by the backend.
- The `Message-ID` is stored in `outreach_events.message_id`.
- This enables reliable reply and thread matching via IMAP.

### 4.4 Email Content Security

- Email bodies must not contain user-supplied HTML that has not been sanitized.
- If HTML emails are supported, all user-editable content must be escaped before inclusion in the email body.
- LLM-generated content must be treated as untrusted input and validated for length and character encoding before sending.

---

## 5. Privacy

### 5.1 Personal Data Handling

The application stores personal data: names, email addresses, LinkedIn URLs. As this is a single-user application used for professional outreach:

- Contact data must not be shared with third-party services beyond what is explicitly required (Reoon for verification, Zoho for sending, Gemini for draft generation).
- When calling the Gemini API, the minimum necessary contact context should be included in prompts. Full database exports must not be sent to external AI services.
- The user is responsible for ensuring their outreach activity complies with applicable laws (CAN-SPAM, GDPR where applicable).

### 5.2 Contact Suppression

- The `contacts.suppressed` flag provides a local suppression mechanism.
- Suppressed contacts must never receive outbound emails.
- If a contact requests to be removed, the user must set `suppressed = 1` with an appropriate reason.
- Suppression is permanent within the system and cannot be automatically reversed.

### 5.3 Data Retention

- The application does not implement automatic data expiration in the initial version.
- The user is responsible for periodically reviewing and cleaning stale data.

---

## 6. Suppression Rules

Suppression is tracked directly on primary database entities rather than in a separate `suppression_list` table:
- Contact-level suppression: `contacts.suppressed = 1`, with `suppressed_reason` and `suppressed_at`.
- Thread-level suppression: `outreach_threads.status = 'suppressed'`.
- Address-level suppression: Hard bounce records in `bounces` table, or `invalid`/`unknown` status in `email_verifications`.

The following conditions must permanently block outreach for a contact:

| Condition | Action |
|-----------|--------|
| `contacts.suppressed = 1` | Block all activity for this contact |
| `outreach_threads.status = 'suppressed'` | Block sending on this thread |
| `email_addresses` has a `bounces` record with `bounce_type = 'hard'` | Block use of this address |
| `email_verifications.status = 'invalid'` | Block use of this address |
| `email_verifications.status = 'unknown'` | Block use of this address |
| `email_verifications.status = 'catch-all'` AND `catch_all_approved = 0` | Block use of this address until approved |

Suppression checks must run at draft generation time AND at send time. Suppression can be imposed between generation and sending. All suppression events are recorded immutably in `audit_log`.

---

## 7. Audit Logging

### 7.1 Events That Must Be Logged

| Event Type | Description |
|------------|-------------|
| `opportunity_captured` | A new opportunity was captured via the extension or API |
| `contact_added` | A new contact was added |
| `email_added` | An email address was added to a contact |
| `email_verified` | An email address was verified via Reoon |
| `catch_all_approved` | A user approved a catch-all email address |
| `draft_generated` | A draft was generated by an LLM |
| `draft_edited` | A draft was manually edited |
| `draft_approved` | A draft was approved for sending |
| `email_sent` | An email was successfully sent |
| `followup_scheduled` | A follow-up was scheduled |
| `followup_suppressed` | A follow-up was suppressed (e.g., due to a reply) |
| `followup_sent` | A follow-up email was sent |
| `reply_received` | A reply was detected in the inbox |
| `bounce_detected` | A bounce notification was received |
| `contact_suppressed` | A contact was marked as suppressed |
| `sync_completed` | A Google Sheets sync cycle completed |
| `sync_conflict` | A sync conflict was detected |
| `send_blocked` | A send was blocked (quota, pause, suppression, missing approval) |
| `global_pause_toggled` | The global sending pause was enabled or disabled |

### 7.2 Log Entry Requirements

Each log entry must include:
- `event_type`: The event identifier from the table above.
- `entity_type` and `entity_id`: The primary entity involved.
- `description`: A human-readable summary.
- `metadata`: A JSON object with relevant context (e.g., draft version, LLM provider used, Reoon status).
- `created_at`: The UTC timestamp of the event.

### 7.3 Immutability

The application must not expose any DELETE or UPDATE operations on the audit log. No code path may modify or delete audit log entries.

---

## 8. Provider Restrictions

### 8.1 Gemini API

- Only the Gemini API key provided in `GEMINI_API_KEY` may be used.
- The model to use must be configurable (not hardcoded), defaulting to a stable Gemini model.
- Prompt content must not include raw credentials, database connection strings, or file system paths.

### 8.2 Reoon API

- API calls must use the key in `REOON_API_KEY`.
- The system must track credit consumption and log it.
- If the Reoon API returns an error, the system must not silently treat the address as verified. It must return an error to the user.

### 8.3 Ollama

- Ollama must only be called if `llm_provider = 'ollama'` in `app_config`.
- The Ollama base URL must come from `OLLAMA_BASE_URL`.
- If Ollama is unavailable, the system must return a clear error rather than falling back to Gemini silently.

---

## 9. Safe Sending Controls

### 9.1 Pre-Send Checklist (10 Mandatory Checks)

Before every outbound send, the following 10 checks must be verified programmatically against persistent database records (never relying solely on in-memory counters):

1. ✅ **Exact Version Approval**: An approval record exists in `approvals` referencing the exact current `draft_id`.
2. ✅ **Global Pause Disabled**: The global pause toggle is OFF (`app_config.sending_paused = 'false'`).
3. ✅ **Daily Quota Available**: Today's sent count from `outreach_events` is strictly less than the daily limit (`app_config.daily_sending_limit`, max 20).
4. ✅ **Contact Not Suppressed**: The recipient contact is active (`contacts.suppressed = 0`).
5. ✅ **Address Not Suppressed**: The selected email address has no hard bounce record in `bounces`.
6. ✅ **Verification Eligibility**: The selected email address has a valid verification status (`safe` or approved `catch-all`).
7. ✅ **Catch-All Approval**: If status is `catch-all`, explicit manual approval has been recorded (`catch_all_approved = 1`).
8. ✅ **No Duplicate Recipient**: No existing `outreach_events` record exists for this thread with the same `event_type` and `followup_number`.
9. ✅ **Thread Eligibility**: The outreach thread is active and eligible (`outreach_threads.status` is not suppressed, replied, bounced, or closed).
10. ✅ **Content Integrity**: The draft message content has not changed since approval was granted.

If any check fails, the send is aborted and a `send_blocked` entry is recorded in `audit_log` with the failure reason.

### 9.2 Daily Quota Management

- The daily sent count is stored in the database (via `outreach_events` count for today) rather than in-memory.
- This ensures the quota is correctly enforced after a process restart.
- The quota resets at midnight (local time).

### 9.3 Global Pause

- The global pause flag is stored in `app_config` with key `sending_paused`.
- Toggling it writes an audit log entry: `global_pause_toggled`.
- The scheduler must check this flag before every send attempt.

### 9.4 One Address Per Thread

- The `outreach_threads.selected_email_address_id` is set when the thread is created and must not change.
- The sending code must always use `selected_email_address_id` for dispatch. It must not iterate over all contact email addresses.

---

## 10. Failure Handling

### 10.1 SMTP Failure

- If the SMTP send fails (connection error, authentication failure, rejection): do not create an `outreach_events` record.
- Write an audit log entry: `email_send_failed` with the error message.
- Return a clear error to the caller.
- The daily quota must not be incremented on failure.

### 10.2 IMAP Failure

- If the IMAP poll fails: log the error.
- Do not mark messages as read if processing was incomplete.
- Retry on the next scheduled poll cycle.

### 10.3 LLM Failure

- If the LLM API returns an error: do not create a draft record.
- Return the error to the user.
- The user may retry draft generation.

### 10.4 Reoon Failure

- If Reoon returns an error: do not store a verification result.
- Do not treat the address as verified.
- Return the error to the user.

### 10.5 Google Sheets Failure

- If the Sheets API fails during sync: roll back any partial changes.
- Write an audit log entry with the error.
- Do not update `last_sync_at` if the sync did not complete successfully.

### 10.6 Scheduler Failure

- If the scheduler encounters an error processing a job: log the error.
- Do not mark the follow-up as sent.
- Retry on the next scheduler run.
- If a job fails repeatedly (more than 3 times): mark the follow-up as `error` status and notify via log.
