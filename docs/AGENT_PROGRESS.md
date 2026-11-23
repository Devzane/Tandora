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

## Current Status

- **Current Stage**: Issue 1 — Chrome Extension Identity & Authentication Restriction
- **Current Task**: Task 3 Completed (Issue 1 fully resolved and verified)
- **Outstanding Work**:
  - Issue 2: Reoon Email Verification Integration & Caching Lifecycle
  - Subsequent Stages (Stage 3+)
- **Exact Next Action**:
  - Await user instructions before starting Issue 2.
- **Any Unresolved Errors**:
  - None.
