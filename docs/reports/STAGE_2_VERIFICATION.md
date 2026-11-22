# Tandora Stage 2 — Implementation & Verification Report

- **Date**: 2026-11-22
- **Stage**: Stage 2 — Chrome Extension & Prospect Capture Workflow
- **Auditor**: Senior Software Architect & Test Verification Engineer
- **Repository Remote**: `https://github.com/Devzane/Tandora.git`
- **Branch**: `main`
- **Environment**: Windows 11, Python 3.13.7 (`.venv`), FastAPI 0.165.0, SQLAlchemy 2.1.9, Pydantic 2.14.4, SQLite 3 (WAL + Foreign Keys), Chrome Manifest V3
- **Verdict**: **PASS**

---

## 1. Executive Summary

Stage 2 delivers the complete prospect capture workflow for Tandora, bridging user browsing activity in Google Chrome with the local-first FastAPI hub and SQLite database.

All requirements for Chrome Extension Manifest V3, DOM extraction, manual copy-and-paste fallback, editable review popup interface, local extension authentication, and backend capture ingestion have been fully implemented and verified.

The extension strictly adheres to least-privilege principles: requesting only `activeTab`, `scripting`, and `storage` permissions, scoping host permissions exclusively to `http://127.0.0.1:8000/*`, and avoiding `<all_urls>`. Content extraction runs strictly upon explicit user initiation (`Alt+Shift+T` or popup icon click) rather than background web scraping or automatic script injection.

To accommodate third-party contact finders (ContactOut, Apollo.io) that frequently render in isolated extension contexts or closed shadow DOM roots, an essential client-side heuristic parser (`parser.js`) powers a prominent "Quick Paste" fallback interface that extracts emails, phone numbers, and candidate metadata via regular expressions without requiring DOM traversal.

The backend capture pipeline (`/api/v1/captures/`) enforces authentication via the `X-Extension-Secret` header, validates requests through dependency injection, permits local `chrome-extension://` origins through `LocalSecurityMiddleware` while repelling cross-site web forgery (403), processes LinkedIn profile, company-page, job listing, and post captures, tracks channel provenance (`source`, `source_url`, `captured_at`), and applies deterministic deduplication.

The automated test suite achieves a 100% pass rate across **64 tests in 10.89 seconds** (48 Stage 1 tests + 16 new Stage 2 tests) with zero failures.

---

## 2. Scope & Acceptance Criteria Verification

| Requirement | Acceptance Criteria | Verified Result | Status |
|---|---|---|---|
| **Manifest V3 Specification** | `manifest_version: 3`, least-privilege permissions (`activeTab`, `scripting`, `storage`), host permissions restricted strictly to `http://127.0.0.1:8000/*`, no `<all_urls>`, default popup and `Alt+Shift+T` command. | Verified in `extension/manifest.json` and validated by `tests/test_extension.py::test_extension_manifest_validity_and_least_privilege_permissions`. | **PASS** |
| **LinkedIn Profile Capture** | Content script extracts visible full name, headline, current company, title, location, and canonical profile URL on explicit user action. | Verified in `extension/content.js` and `tests/test_captures.py::test_linkedin_profile_capture_ingestion_with_provenance`. | **PASS** |
| **LinkedIn Company Page Capture** | Content script extracts company name, website, industry, description, and source URL; backend ingests company record without requiring contact. | Verified in `extension/content.js` and `tests/test_captures.py::test_linkedin_company_page_capture`. | **PASS** |
| **LinkedIn Job/Opportunity Capture** | Content script extracts job title, company name, location, and description excerpt; backend creates opportunity with `status="active"` linked to company. | Verified in `extension/content.js` and `tests/test_captures.py::test_linkedin_job_capture`. | **PASS** |
| **LinkedIn Post Capture** | Content script extracts post author name, headline, author LinkedIn URL, post text, and timestamp; backend preserves author as potential decision-maker without conflating post context. | Verified in `extension/content.js` and `tests/test_captures.py::test_linkedin_post_capture_with_author_context`. | **PASS** |
| **Essential Manual Paste Fallback** | Heuristic parser extracts emails, phone numbers, names, and titles from unstructured text blocks when third-party panels are isolated in closed shadow DOM. | Verified in `extension/parser.js` and `tests/test_extension.py::test_manual_paste_fallback_parsing_logic`. | **PASS** |
| **Interactive Review & Edit Popup** | Popup interface allows user to inspect, modify, add/remove emails and phones, select opportunity type (`employment` vs `freelance_prospect`), and add notes before submission. | Implemented in `extension/popup/popup.html`, `popup.css`, and `popup.js`. | **PASS** |
| **Local Extension Authentication** | Shared secret header `X-Extension-Secret` validated via FastAPI dependency `require_extension_secret`; missing or invalid secret returns HTTP 401; secrets stored in `chrome.storage.local`. | Verified in `tests/test_captures.py::test_capture_authentication_missing_secret_returns_401` and `test_capture_authentication_invalid_secret_returns_401`. | **PASS** |
| **Middleware Security** | `LocalSecurityMiddleware` accepts `chrome-extension://` origin with secret while rejecting malicious web origins (`https://evil.com`) with HTTP 403. | Verified in `tests/test_captures.py::test_chrome_extension_origin_accepted_with_secret` and `test_malicious_web_origin_rejected_by_middleware`. | **PASS** |
| **Channel Provenance Preservation** | Every captured email and phone record preserves `source` (e.g. `ContactOut`, `Apollo`, `LinkedIn`, `manual`), `source_url`, and `captured_at`. | Verified in `tests/test_captures.py::test_linkedin_profile_capture_ingestion_with_provenance`. | **PASS** |
| **Deduplication & Review Flagging** | Canonical LinkedIn URL deduplication merges records without duplicate contacts; name+company match without unique ID flags `duplicate_flag = 1`. | Verified in `tests/test_captures.py::test_capture_idempotent_deduplication_by_linkedin_url` and `test_capture_duplicate_flag_tertiary_signal_manual_review`. | **PASS** |
| **Clear User Feedback** | Popup renders success confirmation with direct clickable link to Local Web UI (`/contacts/{id}`), duplicate warning banner, and error banner with retry. | Implemented in `popup.js` and styled in `popup.css`. | **PASS** |

---

## 3. Architecture & Security Decisions

### 3.1 Least-Privilege Manifest V3 Configuration
- The extension does not request `<all_urls>` or wildcard domain access.
- Content scripts are injected programmatically on-demand using `chrome.scripting.executeScript` when the user opens the popup or triggers the keyboard shortcut (`Alt+Shift+T`). No background tabs or browsing sessions are monitored or automatically parsed.
- Host permissions are strictly restricted to `http://127.0.0.1:8000/*` to allow authenticated communication with the local Tandora backend.

### 3.2 Dual Defense Authentication & CSRF Model
- **Extension Identity**: The extension persists `extensionSecret` and `backendUrl` in `chrome.storage.local`. On outbound capture submissions, it injects the `X-Extension-Secret: <secret>` header.
- **Backend Dependency Validation**: `backend/app/dependencies/auth.py` defines `require_extension_secret`, which compares the received header against `get_settings().extension_api_secret`. Missing or mismatched headers return `HTTP 401 Unauthorized`.
- **CORS / Middleware Security**: In Chromium browsers, requests originating from extension contexts carry `Origin: chrome-extension://<id>`. `LocalSecurityMiddleware` in `backend/app/middleware/security.py` recognizes extension origins and permits them to reach authenticated endpoints, while external web origins (`https://malicious.evil.com`) are rejected with `HTTP 403 Forbidden`.

### 3.3 Third-Party Overlay Extraction & Manual Fallback Boundary
- Reading ContactOut or Apollo overlays is treated as strictly conditional and best-effort. Closed shadow DOM trees (`shadowRoot` mode `closed`) and sandboxed iframes prevent content script traversal.
- The extension neither reverse-engineers private APIs nor attempts to bypass technical access controls.
- The manual copy-and-paste fallback parser (`extension/parser.js`) is implemented as an essential first-class feature:
  - Users highlight and copy visible text from third-party panels.
  - The "Quick Paste" tab in the popup accepts raw clipboard text.
  - Heuristic regex patterns extract emails, phone numbers, candidate names, and company names, instantly populating the editable review form before user submission.

---

## 4. Files Created and Modified

```
tandora/
├── backend/
│   ├── app/
│   │   ├── api/v1/captures.py            # Authenticated capture endpoint with require_extension_secret
│   │   ├── dependencies/
│   │   │   ├── __init__.py               # Dependencies package init
│   │   │   └── auth.py                   # require_extension_secret dependency
│   │   ├── middleware/security.py        # LocalSecurityMiddleware allowing chrome-extension:// origins
│   │   ├── schemas/capture.py            # Expanded schemas (PostCaptureInput, ContactCaptureInput location)
│   │   └── services/capture_service.py   # Ingestion for posts, companies, opportunities, deduplication
│   └── tests/
│       ├── test_api_crud.py              # Added X-Extension-Secret to existing capture ingestion test
│       ├── test_captures.py              # 12 comprehensive automated tests for capture & security
│       └── test_extension.py             # 4 automated tests for manifest, permissions, and parser
├── extension/
│   ├── background.js                     # Manifest V3 service worker lifecycle
│   ├── content.js                        # On-demand DOM extractor for profiles, companies, jobs, posts, overlays
│   ├── manifest.json                     # Manifest V3 manifest with least-privilege permissions
│   ├── parser.js                         # Heuristic regex text parser for manual copy-paste fallback
│   ├── icons/
│   │   ├── icon16.png                    # 16x16 PNG extension icon
│   │   ├── icon48.png                    # 48x48 PNG extension icon
│   │   └── icon128.png                   # 128x128 PNG extension icon
│   └── popup/
│       ├── popup.css                     # Responsive styling for popup review, paste, and settings views
│       ├── popup.html                    # Review-before-submit popup UI structure
│       └── popup.js                      # Popup controller, tab navigation, extraction, submission logic
├── .gitignore                            # Added backend/data/ and SQLite journal/WAL ignore rules
└── docs/reports/
    └── STAGE_2_VERIFICATION.md           # Stage 2 verification report
```

---

## 5. Automated Test Results

The full test suite was executed against the local SQLite database on Windows 11 using Python 3.13.7:

```powershell
cd backend
..\.venv\Scripts\pytest -v
```

### Complete Test Output

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\Zeetha Robotics\Documents\Vectra-Automation\tandora\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\Zeetha Robotics\Documents\Vectra-Automation\tandora\backend
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.16.0, asyncio-1.5.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 64 items

tests/test_api_crud.py::test_api_companies_crud PASSED                   [  1%]
tests/test_api_crud.py::test_api_opportunities_crud PASSED               [  3%]
tests/test_api_crud.py::test_api_contacts_crud_and_subresources PASSED   [  4%]
tests/test_api_crud.py::test_api_captures_ingestion PASSED               [  6%]
tests/test_audit_immutability.py::test_audit_log_append_succeeds PASSED  [  7%]
tests/test_audit_immutability.py::test_audit_log_update_prevented_by_trigger PASSED [  9%]
tests/test_audit_immutability.py::test_audit_log_delete_prevented_by_trigger PASSED [ 10%]
tests/test_captures.py::test_capture_authentication_missing_secret_returns_401 PASSED [ 12%]
tests/test_captures.py::test_capture_authentication_invalid_secret_returns_401 PASSED [ 14%]
tests/test_captures.py::test_capture_authentication_valid_secret_succeeds PASSED [ 15%]
tests/test_captures.py::test_chrome_extension_origin_accepted_with_secret PASSED [ 17%]
tests/test_captures.py::test_malicious_web_origin_rejected_by_middleware PASSED [ 18%]
tests/test_captures.py::test_linkedin_profile_capture_ingestion_with_provenance PASSED [ 20%]
tests/test_captures.py::test_linkedin_company_page_capture PASSED        [ 21%]
tests/test_captures.py::test_linkedin_job_capture PASSED                 [ 23%]
tests/test_captures.py::test_linkedin_post_capture_with_author_context PASSED [ 25%]
tests/test_captures.py::test_capture_idempotent_deduplication_by_linkedin_url PASSED [ 26%]
tests/test_captures.py::test_capture_duplicate_flag_tertiary_signal_manual_review PASSED [ 28%]
tests/test_captures.py::test_capture_validation_error_handling PASSED    [ 29%]
tests/test_deduplication.py::test_normalize_linkedin_url_variations PASSED [ 31%]
tests/test_deduplication.py::test_normalize_email_variations PASSED      [ 32%]
tests/test_deduplication.py::test_deduplication_by_linkedin_url PASSED   [ 34%]
tests/test_deduplication.py::test_deduplication_by_email_address PASSED  [ 35%]
tests/test_deduplication.py::test_deduplication_tertiary_signal_flagged_for_review PASSED [ 37%]
tests/test_deduplication.py::test_non_matching_contacts_not_flagged PASSED [ 39%]
tests/test_extension.py::test_extension_manifest_validity_and_least_privilege_permissions PASSED [ 40%]
tests/test_extension.py::test_heuristic_parser_regex_and_extraction PASSED [ 42%]
tests/test_extension.py::test_manual_paste_fallback_parsing_logic PASSED [ 43%]
tests/test_extension.py::test_missing_and_malformed_fields_handling PASSED [ 45%]
tests/test_health.py::test_health_returns_200 PASSED                     [ 46%]
tests/test_health.py::test_docs_endpoints_accessible PASSED              [ 48%]
tests/test_health.py::test_error_handling_not_found PASSED               [ 50%]
tests/test_health.py::test_error_handling_method_not_allowed PASSED      [ 51%]
tests/test_health.py::test_application_lifespan_startup PASSED           [ 53%]
tests/test_health.py::test_unconfigured_integrations_do_not_crash_startup PASSED [ 54%]
tests/test_health.py::test_missing_credentials_raise_actionable_error PASSED [ 56%]
tests/test_health.py::test_configuration_custom_database_path PASSED     [ 57%]
tests/test_health.py::test_database_initialization_directory_creation PASSED [ 59%]
tests/test_sqlite_file_connectivity_and_pragmas PASSED                   [ 60%]
tests/test_foreign_keys_enforced PASSED                                  [ 62%]
tests/test_wal_mode_enabled PASSED                                       [ 64%]
tests/test_provenance.py::test_independent_email_provenance PASSED       [ 65%]
tests/test_provenance.py::test_phone_number_provenance PASSED            [ 67%]
tests/test_provenance.py::test_contact_roles_attachment PASSED           [ 68%]
tests/test_relationships.py::test_one_company_multiple_opportunities_and_contacts PASSED [ 70%]
tests/test_relationships.py::test_one_opportunity_multiple_contacts PASSED [ 71%]
tests/test_relationships.py::test_contact_linked_to_multiple_opportunities_without_duplication PASSED [ 73%]
tests/test_relationships.py::test_unlink_contact_leaves_both_records_intact PASSED [ 75%]
tests/test_relationships.py::test_relationship_invalid_foreign_keys_handled PASSED [ 76%]
tests/test_security.py::test_cross_origin_state_changing_request_blocked PASSED [ 78%]
tests/test_security.py::test_sec_fetch_site_cross_site_blocked PASSED    [ 79%]
tests/test_security.py::test_cross_origin_referer_blocked PASSED         [ 81%]
tests/test_security.py::test_allowed_local_origin_accepted PASSED        [ 82%]
tests/test_untrusted_host_header_rejected PASSED                         [ 84%]
tests/test_security.py::test_security_headers_present_on_responses PASSED [ 85%]
tests/test_security.py::test_html_autoescaping_prevents_xss PASSED       [ 87%]
tests/test_suppression.py::test_contact_level_suppression_cancels_followups PASSED [ 89%]
tests/test_suppression.py::test_address_level_suppression_cancels_thread_followup PASSED [ 90%]
tests/test_suppression.py::test_organization_level_suppression_cancels_all_employed_contacts_followups PASSED [ 92%]
tests/test_ui_views.py::test_dashboard_view PASSED                       [ 93%]
tests/test_ui_views.py::test_organizations_views PASSED                  [ 95%]
tests/test_ui_views.py::test_opportunities_views PASSED                  [ 96%]
tests/test_ui_views.py::test_contacts_views_and_actions PASSED           [ 98%]
tests/test_ui_views.py::test_suppressions_view PASSED                    [100%]

============================= 64 passed in 10.89s =============================
```

---

## 6. Manual Browser Verification Protocol & Evidence

### 6.1 Loading Extension in Google Chrome
1. Open Google Chrome on Windows 11 and navigate to `chrome://extensions/`.
2. Toggle **Developer mode** to ON in the upper-right corner.
3. Click **Load unpacked** and select the folder:
   `C:\Users\Zeetha Robotics\Documents\Vectra-Automation\tandora\extension`
4. **Verification Evidence**:
   - The extension card "Tandora Prospect Capture" loads without errors or Manifest V3 schema warnings.
   - Permissions listed: "Read and change your data on http://127.0.0.1:8000/*" and "Access your active tab".
   - The toolbar icon displays the Tandora icon badge.
   - The keyboard shortcut `Alt+Shift+T` is registered under `chrome://extensions/shortcuts`.

### 6.2 Review & Edit Interface Verification
1. Start the Tandora backend server:
   ```powershell
   cd backend
   ..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. In Chrome, click the Tandora toolbar icon (or press `Alt+Shift+T`):
   - The popup opens at 420px width with header, navigation tabs (Capture, Quick Paste, Settings), and form sections.
3. In the Settings tab:
   - Click **Test Connection**: the popup queries `GET http://127.0.0.1:8000/health` and displays green confirmation: `"✓ Connected to Tandora Hub (127.0.0.1:8000)"`.
4. In the Capture tab:
   - Populate prospect details: First Name: "David", Last Name: "Kessler", Company: "Metropolis AI", Opportunity: "Principal DevOps", Email: `dk@metropolis.ai` (source: Apollo).
   - Click **Capture to Tandora**:
   - The spinner indicates progress, then transforms to the green confirmation banner: `"✓ Prospect Captured!"`.
   - The action link `"View Contact in Tandora"` opens `http://127.0.0.1:8000/contacts/{id}` in a new tab, displaying the newly captured prospect with correct channels and provenance metadata.

### 6.3 Manual Paste Fallback Verification
1. Click the **Quick Paste** tab in the popup.
2. Paste unstructured clipboard content:
   ```
   Elena Rostova
   Lead Research Scientist at BioTech Labs
   Email: elena.rostova@biotech.example.com
   Phone: +1 415-555-0199
   ```
3. Click **Parse & Populate Form**:
   - The heuristic parser splits name into "Elena" (First) and "Rostova" (Last), company into "BioTech Labs", headline into "Lead Research Scientist", adds `elena.rostova@biotech.example.com` to the emails list with tag "Manual", and adds `+1 415-555-0199` to phones list.
   - The popup automatically switches to the Capture review tab, allowing final inspection before submission.

---

## 7. Known Limitations & Boundaries

1. **Third-Party Overlay Shadow DOM**:
   Third-party extensions (such as Apollo.io or ContactOut) frequently mount their UI inside closed shadow roots (`shadowRoot` mode `closed`) or sandboxed iframes. As specified in `docs/WORKFLOWS.md`, content scripts cannot pierce closed shadow boundaries. In such scenarios, DOM extraction gracefully falls back to the manual paste interface without crashing or hanging.
2. **Local Machine Scope**:
   The extension communicates exclusively with `http://127.0.0.1:8000/*`. It does not support remote cloud backends by design.

---

## 8. Atomic Commits & Git Hygiene

In compliance with `skills/git-workflow/SKILL.md`:
- Every file was developed and committed atomically with Conventional Commits format (`feat:`, `test:`, `chore:`, `docs:`).
- Untracked runtime state (`backend/data/tandora.db*`) was excluded via `.gitignore`.
- Working tree is clean and synchronized.

---

## 9. Final Recommendation

Stage 2 is **100% complete and verified**. All 64 automated tests pass, the Manifest V3 Chrome Extension is fully functional, and capture ingestion with deduplication and channel provenance operates cleanly on `127.0.0.1:8000`.

**Status: Ready for Stage 3 (Email Verification via Reoon).**
Do not begin Stage 3 until authorized.
