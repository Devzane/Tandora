# Tandora — Agent Progress Tracker

## Baseline Test Verification

- **Status**: Completed
- **Configuration Used**: `backend/pyproject.toml` (`-c backend/pyproject.toml backend/tests -v`)
- **Total Tests Collected**: 73
- **Passed**: 73
- **Failed**: 0
- **Skipped**: 0
- **Warnings / Errors**: 0
- **Execution Duration**: 5.59s
- **Failed Tests**: None

---

## Issue 1, Task 1: Authentication Security Inspection

- **Status**: Completed
- **Files Inspected**:
  - `extension/manifest.json`, `extension/popup/popup.js`, `extension/background.js`
  - `backend/app/config.py`, `backend/app/dependencies/auth.py`, `backend/app/middleware/security.py`, `backend/app/api/v1/captures.py`
  - `backend/.env`, `backend/.env.example`
  - `backend/tests/test_captures.py`, `backend/tests/test_security.py`, `backend/tests/test_extension.py`
  - `docs/SECURITY_AND_COMPLIANCE.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOWS.md`
- **Identified Gaps**:
  - Lack of deterministic public key in `manifest.json`.
  - Non-constant-time secret comparison in `require_extension_secret`.
  - Missing validation of `CHROME_EXTENSION_ID` format (`^[a-p]{32}$`).

---

## Issue 1, Task 2: Implement Authentication Hardening

- **Status**: Completed
- **Implementation Changes**:
  1. **Constant-Time Secret Comparison**:
     - Updated `backend/app/dependencies/auth.py` to use `secrets.compare_digest` for validating `X-Extension-Secret`.
     - Preserves HTTP 401 Unauthorized for missing or incorrect secrets while eliminating timing side-channels.
     - Never exposes secrets in logs, responses, or error details.
  2. **Chrome Extension ID Validation**:
     - Added `CHROME_EXTENSION_ID_PATTERN = re.compile(r"^[a-p]{32}$")` and `@field_validator("chrome_extension_id")` to `backend/app/config.py`.
     - Rejects malformed extension IDs during startup/instantiation with actionable error messages without exposing sensitive settings.
     - Automatically normalizes valid extension IDs to lowercase.
  3. **Stable Extension Identity**:
     - Generated a standard RSA 2048 key pair.
     - Placed only the public key (DER SubjectPublicKeyInfo base64-encoded) into `extension/manifest.json` under `"key"`.
     - Derived the deterministic 32-character `[a-p]` extension ID (`doaipkncpfpmingeoanfpealbjojkmlp`) from the SHA-256 hash of the public key DER.
     - Configured `CHROME_EXTENSION_ID=doaipkncpfpmingeoanfpealbjojkmlp` in `backend/app/config.py`, `backend/.env`, and `backend/.env.example`.
     - Added `*.pem`, `*.key`, and `secrets/` to `.gitignore` to guarantee private signing keys are never tracked or committed.
  4. **Origin Validation**:
     - Preserved expected extension origin enforcement in `backend/app/dependencies/auth.py` and `backend/app/middleware/security.py`.
     - Rejects unauthorized or malformed extension origins with HTTP 403 Forbidden.
     - Rejects malformed URL origins with HTTP 400 Bad Request.
     - Accepts non-browser/testing calls providing the valid secret without compromising browser security.
  5. **Automated Tests Added**:
     - `test_constant_time_comparison_used_for_extension_secret`: Verifies `secrets.compare_digest` invocation during capture auth.
     - `test_valid_chrome_extension_id_configuration`: Verifies `^[a-p]{32}$` format acceptance and normalization.
     - `test_invalid_chrome_extension_id_configuration_rejected`: Tests rejection of non-a-p characters, numbers, and incorrect lengths.
     - `test_manifest_key_presence_and_derived_extension_id`: Validates public key DER structure in `manifest.json` and asserts exact match against configured `CHROME_EXTENSION_ID`.
- **Files Modified**:
  - `backend/app/dependencies/auth.py`
  - `backend/app/config.py`
  - `backend/.env`
  - `backend/.env.example`
  - `extension/manifest.json`
  - `.gitignore`
  - `backend/tests/test_captures.py`
  - `backend/tests/test_extension.py`
  - `docs/AGENT_PROGRESS.md`
- **Tests Executed and Results**:
  - Focused command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests/test_captures.py backend/tests/test_extension.py -v` -> 29 passed in 1.54s.
  - Full suite command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests -v` -> 77 passed in 4.80s (100% pass rate, 0 failures, 0 warnings).
- **Remaining Limitations / Notes**:
  - Chrome requires the extension to be reloaded in `chrome://extensions` for the manifest `"key"` change to take effect.
  - To preserve extension identity across installations, the developer should keep the private signing key in a secure backup outside version control.

---

## Issue 1, Task 3: Final Authentication Security Verification

- **Status**: Completed
- **Private-Key Protection Findings**:
  - **Existence & Location**: The RSA private key exists on local disk at `extension/key.pem` (1,704 bytes).
  - **Git Exclusion**: Safely excluded by `.gitignore` rule line 37 (`*.pem`). Confirmed via `git check-ignore -v extension/key.pem`.
  - **Git Tracking History**: Confirmed that neither `extension/key.pem` nor any other private key file has ever been committed or staged in Git (`git ls-files` and `git log --all -- extension/key.pem` return empty).
  - **Unpacked Extension Sufficiency**: The public key in `extension/manifest.json` under `"key"` (base64-encoded SubjectPublicKeyInfo DER) is 100% sufficient for Chrome unpacked extension development and execution. Chromium derives the deterministic extension ID (`doaipkncpfpmingeoanfpealbjojkmlp`) directly from the manifest public key without requiring the private key.
  - **Storage & Disposal Requirements**: The private key is not needed for the active unpacked development workflow. It is only required if packaging into a standalone `.crx` file or publishing to the Chrome Web Store. The key was preserved intact without modification or deletion. If `.crx` distribution is needed in the future, it should be archived into an encrypted password manager or secure vault outside the repository; otherwise it can be securely purged.
- **Origin Enforcement Test Results**:
  - Expected extension ID + valid secret -> Accepted (HTTP 201).
  - Unexpected extension ID + valid secret -> Rejected with HTTP 403 Forbidden (`Unauthorized extension origin`).
  - Unexpected extension ID + invalid secret -> Rejected with HTTP 403 Forbidden.
  - Missing Origin in browser context (`Sec-Fetch-Site: cross-site`) -> Rejected with HTTP 403 Forbidden (`Cross-site state-changing requests are prohibited`).
  - Browser opaque origin (`Origin: null`) -> Rejected with HTTP 403 Forbidden (`Cross-origin request from 'null' is prohibited`).
  - Missing Origin in non-browser context + valid secret -> Accepted (HTTP 201).
  - Missing Origin in non-browser context + invalid secret -> Rejected with HTTP 401 Unauthorized.
  - Malformed extension origin (`chrome-extension://` without ID) -> Rejected with HTTP 403 Forbidden.
  - Malformed URL origin (`http://[invalid:host`) -> Handled with HTTP 400 Bad Request (`Malformed Origin header`).
  - Correct Origin + missing secret -> Rejected with HTTP 401 Unauthorized (`Invalid or missing extension secret`).
  - Correct Origin + incorrect secret -> Rejected with HTTP 401 Unauthorized (`Invalid or missing extension secret`).
- **Constant-Time Comparison Edge-Case Verification**:
  - **CPython Limitation Identified**: Python's `secrets.compare_digest` (hmac.compare_digest) raises `TypeError: comparing strings with non-ASCII characters is not supported` when compared strings contain non-ASCII characters. Passing a unicode or non-ASCII header previously caused an unhandled 500 error.
  - **Hardening Applied**: Updated `backend/app/dependencies/auth.py` to compare ASCII strings directly with `secrets.compare_digest`, falling back to UTF-8 byte comparison (`cleaned.encode('utf-8')` vs `expected.encode('utf-8')`).
  - **Edge-Case Results**:
    - Correct ASCII secret -> Accepted (HTTP 201).
    - Incorrect ASCII secret -> HTTP 401 Unauthorized in constant time.
    - Empty or whitespace secret (`""`, `"   "`, `"\t\n"`, `None`) -> HTTP 401 Unauthorized.
    - Non-ASCII, unicode, emojis, null bytes, and malformed surrogates (`café_auth_token`, `🔑_secret_key`, `tokën`, `null\x00byte`, `\ud800`) -> Safely rejected with HTTP 401 Unauthorized in constant time without unhandled exceptions or 500 errors.
    - No secret disclosure in error details or log outputs.
- **Final Test Results**:
  - **Command**: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests -v`
  - **Total Tests Collected**: 81
  - **Passed**: 81
  - **Failed**: 0
  - **Skipped**: 0
  - **Warnings / Errors**: 0
  - **Execution Duration**: 9.65s (100% pass rate)
- **Remaining Security Limitations**:
  - The RSA private key remains stored locally on developer disk (`extension/key.pem`), safely git-ignored; it should be migrated to an encrypted secrets vault before multi-user or production deployment.
  - The shared secret is stored client-side in Chrome's `chrome.storage.local`; any attacker with local OS access to the Chromium user profile directory could read the plaintext storage database.
  - Backend loopback testing on Windows requires network/socket permission (`BypassSandbox: true`) because `TestClient`/`anyio` binds local sockets.

---

---

## Issue 2: Reoon Email Verification Integration & Policy Corrections

- **Status**: Completed & Verified
- **Implementation & Correction Details**:
  1. **Approved Verification Policy Enforced**:
     - **Automatic Approval**: `safe`, `catch_all`, and `role_account` are automatically approved (`is_address_usable = True`). For `catch_all`, `catch_all_approved` is automatically set to `1`. No manual review or approval required.
     - **Automatic Suppression**: `invalid`, `unknown`, `disposable`, `spamtrap`, `disabled`, and `inbox_full` (pending recovery policy) are automatically suppressed (`email_addresses.suppressed = 1`).
     - **Address Usability Guard (`is_address_usable`)**: Evaluates `status in ("safe", "catch_all", "role_account")` and verifies the address is not suppressed and verification has not expired. All suppressed, invalid, unknown, disposable, spamtrap, disabled, inbox-full, or unverified addresses return `False`.
     - **Cleaned UI & APIs**: Removed redundant manual approval buttons and endpoints (`approve_catch_all`) that existed solely for the rejected manual gate. Updated `dashboard.html` to track "Suppressed Addresses" and credit usage, and `contact_detail.html` to clearly badge all 9 Power Mode statuses.
  2. **Complete Reoon Power Mode Status Mapping (`DOCUMENTED_POWER_MODE_STATUSES`)**:
     - All 9 documented Power Mode statuses are accounted for:
       - `safe` -> `safe` (Approved)
       - `catch_all` -> `catch_all` (Approved)
       - `role_account` -> `role_account` (Approved)
       - `invalid` -> `invalid` (Suppressed)
       - `unknown` -> `unknown` (Suppressed)
       - `disposable` -> `disposable` (Suppressed)
       - `spamtrap` -> `spamtrap` (Suppressed)
       - `disabled` -> `disabled` (Suppressed)
       - `inbox_full` -> `inbox_full` (Suppressed pending recovery policy)
     - Explicit handling for unexpected provider statuses: mapped safely to `unknown`, suppressed, and flagged via warning log.
     - Preserves complete raw provider payload in `email_verifications.reoon_response` for auditing.
  3. **Configurable Timeout & Technical Failure Isolation**:
     - Added `reoon_timeout_seconds: float = Field(default=90.0, ...)` to `Settings` (`backend/app/config.py`, `backend/.env`, `backend/.env.example`).
     - Reoon Power Mode requests timeout after 90 seconds (configurable for long-running deep SMTP checks).
     - Catch `httpx.TimeoutException` explicitly, raising `ReoonAPIError`.
     - Timeouts, HTTP errors, network drops, and missing credentials raise `ReoonAPIError` and are recorded strictly as technical failures.
     - **No False Classifications**: Technical failures are never recorded as `unknown`, do not create partial records in `email_verifications`, and do not alter `email_addresses.suppressed`.
  4. **Credit Accounting Logic**:
     - Accurately distinguishes between verification requests attempted, successful responses, and credits consumed according to Reoon's billing policy:
       - Conclusive verification (`safe`, `invalid`, `disabled`, `disposable`, `inbox_full`, `catch_all`, `role_account`, `spamtrap`): consumes 1 credit.
       - Inconclusive verification (`unknown`): consumes 0 credits (Reoon waives/refunds credits for inconclusive results).
       - Technical failures / timeouts: consume 0 credits.
     - Raw API responses preserved for audit and reconciliation.
  5. **Automated Tests (`backend/tests/test_email_verification.py`)**:
     - 21 comprehensive tests covering:
       - Automatic approval of `safe`, `catch_all`, and `role_account`.
       - Automatic suppression of `invalid`, `unknown`, `disposable`, `spamtrap`, `disabled`, and `inbox_full`.
       - All 9 documented Reoon Power Mode statuses.
       - Unexpected provider response mapping and handling.
       - Configurable timeout handling and exception isolation.
       - Technical failure isolation (HTTP errors, timeouts, invalid payloads do not touch database or suppress address).
       - Credit accounting (0 for unknown, 1 for conclusive).
       - 30-day cache lifecycle, cache hits, cache bypass (`force=True`), and cache expiration.
       - Usability matrix verification for outreach safety.
  6. **Security & Concurrency Fixes Implemented**:
     - **Fix 1: Keyed-Lock Concurrency Synchronization (`backend/app/services/verification_service.py`)**:
       - Implemented `KeyedMutexRegistry` providing thread-safe, reference-counted locks keyed by `email_address_id`.
       - Prunes lock entries automatically upon completion to prevent unbounded memory growth.
       - Implemented double-checked locking: when a request acquires the mutex, it invalidates its session cache (`db.expire_all()`) and checks the 30-day cache again.
       - If a concurrent request completed verification, the waiting thread immediately reuses the committed result (`was_cached=True`) without calling the external Reoon API or consuming credits.
       - Guarantees `db.commit()` occurs before releasing the mutex.
       - Scope limitation: In-process synchronization for single-process architectures (does not claim cross-process / multi-host distribution).
     - **Fix 2: Reoon Credential Leakage Prevention (`backend/app/integrations/reoon.py`)**:
       - Replaced direct logging of `httpx.HTTPStatusError` and `httpx.RequestError` objects.
       - Stripped request URLs and query parameters (`key=<API_KEY>`) from log statements.
       - Raising `ReoonAPIError` outside `except` blocks detaches underlying `httpx` exceptions from `__context__` entirely (`__context__ is None`), in addition to `__suppress_context__ = True` via `raise ... from None`.
       - Implemented `_sanitize_provider_reason()` to explicitly redact API keys, URLs, and query parameters from provider-returned error reason strings (`{"status": "error", "reason": "..."}`).
       - Logs only sanitized HTTP status codes (`logger.error("Reoon API request failed with HTTP status %d", status_code)`) and connection error class names.
- **Files Created / Modified**:
  - `backend/app/config.py` (added `reoon_timeout_seconds`)
  - `backend/.env` & `backend/.env.example`
  - `backend/app/integrations/reoon.py` (`_sanitize_provider_reason`, credential sanitization, `__context__` detachment)
  - `backend/app/services/verification_service.py` (`KeyedMutexRegistry`, double-checked caching, transaction boundary commit, restored policy, 9-status mapping, credit accounting)
  - `backend/app/schemas/email_verification.py` (updated stats schema and credit reconciliation description)
  - `backend/app/api/v1/email_verification.py` (removed manual catch-all gate endpoint, updated verification flow)
  - `backend/app/ui/routes.py`
  - `backend/app/templates/contact_detail.html`
  - `backend/app/templates/dashboard.html`
  - `backend/tests/test_email_verification.py` (added concurrency, lock lifecycle, edge-case, and credential protection regression tests)
  - `docs/AGENT_PROGRESS.md`
- **Tests Executed and Results**:
  - Focused command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests/test_email_verification.py -v` -> 34 passed in 5.65s.
  - Full suite command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests -v` -> 115 passed in 13.30s (100% pass rate, 0 failures, 0 warnings).

---

## Stage 4, Task 1: LLM Provider Abstraction and Clients

- **Status**: Completed
- **Implementation Scope**:
  1. **Provider Abstraction (`backend/app/providers/llm_interface.py`)**:
     - Defined `LLMProvider` runtime protocol with `generate(prompt: str) -> DraftResult` contract.
     - Implemented immutable frozen dataclass `DraftResult` (`text`, `provider`, `model`, `raw_prompt`) with `.content` and `.model_used` convenience aliases.
     - Defined `LLMGenerationError(Exception)` for unified generation failure handling across providers.
  2. **Google Gemini REST Client (`backend/app/integrations/gemini.py`)**:
     - Official REST endpoint `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`.
     - Secure header-based authentication using `x-goog-api-key` (API key never placed in URL or query params).
     - Configurable model (default `gemini-3.5-flash-lite`, with `gemini-3.8-flash` supported as alternative; Gemini 1.5 Flash retired), configurable timeout (default 60.0s).
     - Prompt validation rejecting empty or whitespace-only inputs.
     - Defensive parsing of response candidates, safety finish-reasons, and error payloads.
     - Credential sanitization in error messages, redacting keys, URLs, and control characters.
     - Exception context detachment (`raise ... from None` with variable decoupling) to ensure `__context__ is None`.
  3. **Local Ollama REST Client (`backend/app/integrations/ollama.py`)**:
     - Local REST endpoint `POST {base_url}/api/generate` with `stream: False`.
     - Configurable `ollama_base_url` (default `http://127.0.0.1:11434`), model (default `llama3.2`), and timeout (default 60.0s).
     - Graceful handling of local service unavailability (`httpx.ConnectError`), timeouts, HTTP errors, and malformed responses.
     - Same immutable `DraftResult` return contract.
  4. **Provider Factory (`backend/app/providers/llm_factory.py`)**:
     - `get_llm_provider(provider_name: str | None = None, **kwargs) -> LLMProvider`.
     - Resolves configured provider (`settings.llm_provider`) by default or explicit per-request override.
     - Case-insensitive resolution for `"gemini"` and `"ollama"`.
     - Rejects unsupported providers with descriptive `ValueError`.
     - Lazy credential validation: missing Gemini API key raises `MissingCredentialError` at resolution time without crashing app startup.
     - Does not mutate global application settings during per-request provider selection.
  5. **Configuration (`backend/app/config.py` & `backend/.env.example`)**:
     - Added `gemini_model` (default `"gemini-3.5-flash-lite"`; Gemini 1.5 Flash retired; `gemini-3.8-flash` alternative).
     - Added `ollama_model` (default `"llama3.2"`).
     - Added `llm_timeout_seconds` (default `60.0`).
     - Maintained existing `ollama_base_url` (`"http://127.0.0.1:11434"`).
  6. **Automated Testing (`backend/tests/test_llm_providers.py`)**:
     - 21 focused tests covering protocol conformance, DraftResult immutability, default model verification (`gemini-3.5-flash-lite`), explicit model overrides (`gemini-3.8-flash`), Gemini headers/endpoints/errors/safety/sanitization, Ollama local generation/unavailability/timeouts, factory runtime selection, case insensitivity, and credential protection.
     - Zero live network calls (100% mocked HTTP transport).
- **Files Created / Modified**:
  - `backend/app/config.py`
  - `backend/.env.example`
  - `backend/app/providers/__init__.py`
  - `backend/app/providers/llm_interface.py`
  - `backend/app/providers/llm_factory.py`
  - `backend/app/integrations/__init__.py`
  - `backend/app/integrations/gemini.py`
  - `backend/app/integrations/ollama.py`
  - `backend/tests/test_llm_providers.py`
  - `docs/ARCHITECTURE.md`
  - `docs/PROJECT_SPECIFICATION.md`
  - `docs/DATABASE_SCHEMA.md`
  - `docs/AGENT_PROGRESS.md`
- **Tests Executed and Results**:
  - Focused command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests/test_llm_providers.py -v` -> 21 passed in 1.95s.
  - Full suite command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests -v` -> 136 passed (100% pass rate, 0 failures, 0 warnings).

---

## Stage 4, Task 2: Context Assembly and Prompt Engine

- **Status**: Completed
- **Implementation Scope**:
  1. **Context Assembly (`backend/app/services/draft_service.py`)**:
     - Implemented `assemble_context(db, thread_id) -> AssembledContext` retrieving structured context for an existing `OutreachThread`:
       - **Company** (`CompanyContext`): `name`, `description`, `industry`, `website` (falls back to contact's company when opportunity company is absent).
       - **Opportunity** (`OpportunityContext`): `title`, `type`, `description`, `source_url`.
       - **Contact** (`ContactContext`): `full_name`, `first_name`, `headline`, `notes`, deduplicated sorted `roles` (`ContactRole`). Explicitly excludes recipient email addresses, phone numbers, and unnecessary PII.
       - **LinkedIn Evidence** (`LinkedInEvidence`): deduplicated `post_text`, `author_headline`, `post_url` (scoped to `opportunity_id == opp.id` or unattached `author_contact_id == contact.id` to avoid cross-opportunity leakage).
     - Preserves missing optional fields as `None` / empty tuples without fabricating data.
     - Exposes `has_sufficient_context` and JSON-serializable `to_dict()` for user review alongside generated drafts.
  2. **Prompt Construction & Injection Defense (`build_prompt`)**:
     - Enforces a strict three-paragraph outreach structure (personalized opening, relevant business problem/opportunity without stating unverified assumptions as facts, concise sender contribution + CTA) and anti-hallucination rules (never invent clients, results, statistics, interactions, qualifications, or capabilities; avoid generic flattery; never disclose that the message was derived from a job post, LinkedIn profile, or captured data).
     - Handles sparse/insufficient context via an explicit trusted `SPARSE CONTEXT DIRECTIVE` instructing a brief, exploratory message without fabrication.
     - Isolates `<TRUSTED_SYSTEM_RULES>`, optional `<USER_STYLE_PREFERENCES>`, `<UNTRUSTED_REFERENCE_DATA>`, and `<OUTPUT_FORMAT>` using unique XML-style delimiter tags, stripping unsafe control characters and escaping embedded delimiter breakouts (`[TAG_REMOVED]`).
     - Designates all retrieved database fields (company descriptions, contact notes, opportunity descriptions, LinkedIn posts) and custom generation instructions as untrusted inputs that cannot override core rules or factual accuracy.
  3. **Structured Output Parsing & Validation (`parse_draft_output`, `validate_draft`, `generate_draft_from_context`)**:
     - `parse_draft_output()` defensively handles raw JSON, single Markdown-fenced JSON blocks, and minor surrounding prose/extra keys, while rejecting missing fields, non-string types, empty values, malformed JSON, multiple code fences, and ambiguous multi-object outputs via `DraftValidationError(LLMGenerationError, ValueError)`.
     - `validate_draft()` validates non-empty single-line `subject` (5–150 characters), `body` (50–2,500 characters), exactly 3 paragraphs, absence of null bytes/header newlines in subject, and rejection of unresolved placeholders (`[COMPANY]`, `[NAME]`, `[RECIPIENT]`, `[INSERT]`, `[Company Name]`, `{{name}}`, `{company}`, `<NAME>`, `TODO`, `TBD`, `FIXME`, and generic uppercase bracketed tokens).
     - `generate_draft_from_context()` connects `build_prompt`, `get_llm_provider`/`LLMProvider`, `parse_draft_output`, and `validate_draft` uniformly for both Gemini and Ollama without persisting drafts or modifying thread state.
  4. **Service Exports (`backend/app/services/__init__.py`)**:
     - Exported `AssembledContext`, `CompanyContext`, `ContactContext`, `DraftValidationError`, `GeneratedDraftPreview`, `LinkedInEvidence`, `OpportunityContext`, `assemble_context`, `build_prompt`, `generate_draft_from_context`, `parse_draft_output`, and `validate_draft`.
  5. **Automated Tests (`backend/tests/test_draft_service.py`)**:
     - Added 57 unit/integration tests (with 100% mocked LLM HTTP transport; zero live API calls and zero draft DB persistence) covering all 20 required scenarios plus boundary, security, delimiter-escape, provider-contract, and log-redaction checks.
- **Files Created / Modified**:
  - `backend/app/services/draft_service.py`
  - `backend/app/services/__init__.py`
  - `backend/tests/test_draft_service.py`
  - `docs/AGENT_PROGRESS.md`
- **Tests Executed and Results**:
  - Focused command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests/test_draft_service.py -v` -> 57 passed in 2.16s.
  - Full suite command: `.venv\Scripts\pytest -c backend/pyproject.toml backend/tests -v` -> 193 passed in 12.03s (0 failed, 0 skipped, 0 warnings).
- **Known Limitations**:
  - Prompt injection cannot be eliminated completely through prompt boundaries alone; structural delimiters and instructions reduce risk, and human review of generated drafts against the preserved `AssembledContext` remains mandatory.
  - Automated placeholder and structural validation checks formatting, length bounds, paragraph count, and common template tokens, but cannot guarantee factual accuracy or absence of hallucinations.
  - `contact_roles` in the current schema stores role/department descriptors in a single `role` column (no separate `department` database column exists).
  - Draft persistence, versioning, manual editing, REST endpoints, and UI integration are scoped for Stage 4 Tasks 3–4.

---

## Stage 4, Task 3: Thread Initialization, Draft Persistence and Version Management

- **Status**: Completed
- **Implementation Scope**:
  1. **Database Constraints & Reversible Alembic Migration (`backend/app/models/draft.py`, `backend/alembic/versions/7f420d53dd47_add_partial_unique_index_for_initial_.py`)**:
     - Added SQLite partial unique index `uq_drafts_initial_version` on `drafts (outreach_thread_id, draft_type, version) WHERE draft_type = 'initial' AND followup_number IS NULL` to close SQLite's `NULL != NULL` uniqueness gap while preserving `followup_number = NULL` for initial drafts and keeping `uq_drafts_thread_version` intact for follow-up drafts.
     - Verified Alembic `upgrade head` (`4a386b6fd0d9 -> 7f420d53dd47`), `downgrade -1` (`7f420d53dd47 -> 4a386b6fd0d9`), and re-`upgrade head` cleanly.
  2. **Thread Initialization & Eligibility Validation (`backend/app/services/draft_service.py`)**:
     - Implemented `validate_recipient_eligibility()` checking entity existence, email-to-contact ownership (`email_obj.contact_id == contact.id`), multi-level suppression (`contact`, `opportunity.company`, `contact.company`, `email_address`), and `is_address_usable()` (preserving Stage 3 policy: `safe`, `catch-all`, `role_account` usable when unexpired; rejecting `invalid`, `unknown`, `disposable`, `spamtrap`, `disabled`, `inbox_full`, unverified, and expired).
     - Implemented `initialize_outreach_thread()` returning existing thread idempotently when `selected_email_address_id` matches, raising `ThreadConflictError` if a different email is requested (never silently replacing the recipient), and protecting against concurrent races via `BEGIN IMMEDIATE` + `uq_outreach_threads_opp_contact`.
  3. **Persistent Draft Generation & Atomic Versioning (`generate_and_persist_draft`, `redact_prompt_for_audit`)**:
     - Validates thread status (`suppressed`, `replied`, `bounced`, `closed`, `sending` blocked; `sent` blocked for `initial` drafts) and rechecks recipient eligibility both before calling the LLM provider and inside the write transaction.
     - Runs `assemble_context()`, `build_prompt()`, `LLMProvider.generate()`, `parse_draft_output()`, and `validate_draft()` outside database write locks.
     - Stores `redact_prompt_for_audit()` in `Draft.generation_prompt`, replacing all retrieved database fields and custom instructions with `[REDACTED]` / `[REDACTED_CUSTOM_INSTRUCTIONS]`.
     - Serializes version allocation per `(outreach_thread_id, draft_type, followup_number)` via auxiliary in-process `KeyedMutexRegistry` (`_draft_lock_registry`) plus SQLite `BEGIN IMMEDIATE` write transactions (or nested savepoints when inside an active caller-managed transaction), always setting `is_edited=0`. Failed generation never persists a draft or consumes a version number.
  4. **Draft & Thread Retrieval (`get_outreach_thread`, `get_draft`, `list_draft_versions`, `get_latest_draft`)**:
     - Implemented deterministic ordering and strict isolation between `initial` (`followup_number IS NULL`) and `followup` (`1..3`) drafts.
  5. **Append-Only Audit Logging**:
     - Records `outreach_thread_created`, `draft_generated`, and `draft_generation_failed` events using `write_audit_log()`, storing only structural IDs/provider/model/error-class metadata and excluding API keys, credentials, email addresses, contact notes, complete prompts, and full generated bodies.
  6. **Service Exports & Tests (`backend/app/services/__init__.py`, `backend/tests/test_draft_persistence.py`)**:
     - Added 36 tests covering all 27 required scenarios (thread init, idempotency, conflicts, ownership, multi-level suppression, Stage 3 verification policy, initial/follow-up persistence, version isolation, failure non-consumption, historical immutability, retrieval, concurrent multi-thread allocation, audit redaction, transaction rollback & caller-tx safety, partial unique index enforcement, and Alembic upgrade/downgrade roundtrip).
- **Files Created / Modified**:
  - `backend/app/models/draft.py`
  - `backend/alembic/versions/7f420d53dd47_add_partial_unique_index_for_initial_.py`
  - `backend/app/services/draft_service.py`
  - `backend/app/services/__init__.py`
  - `backend/tests/test_draft_persistence.py`
  - `docs/AGENT_PROGRESS.md`
- **Tests Executed and Results**:
  - Focused command: `.\.venv\Scripts\pytest -c backend/pyproject.toml backend/tests/test_draft_persistence.py -v` -> 36 passed in 11.77s.
  - Full suite command: `.\.venv\Scripts\pytest -c backend/pyproject.toml backend/tests -v` -> 229 passed in 36.74s (0 failed, 0 skipped, 0 warnings).
- **Known Limitations**:
  - In-process `KeyedMutexRegistry` reduces thread contention inside one Python process; cross-process concurrency relies on SQLite `BEGIN IMMEDIATE` write-lock serialization and database uniqueness constraints (`uq_drafts_initial_version`, `uq_drafts_thread_version`, `uq_outreach_threads_opp_contact`).
  - Manual draft editing, approval SHA-256 hashing, SMTP sending, REST endpoints, and UI views remain out of scope and deferred to subsequent tasks/stages.

---

## Current Status

- **Current Stage**: Stage 4 — AI Draft Generation Engine
- **Current Task**: Task 3 Completed (Thread Initialization, Draft Persistence and Version Management)
- **Outstanding Work**:
  - Stage 4, Task 4: UI Integration and Manual Review
  - Subsequent Stages (Stages 5 to 9)
- **Exact Next Action**:
  - Await user review and authorization before proceeding to Stage 4, Task 4.
- **Any Unresolved Errors**:
  - None.
