---
name: chrome-extension
description: Chrome Extension Manifest V3 engineering for Tandora — LinkedIn profiles, posts, ContactOut/Apollo visible overlay extraction, manual paste fallback, least-privilege permissions, and secure local capture.
risk: low
source: project
date_added: '2026-11-21'
---

# Chrome Extension Skill — Tandora

## Purpose

This skill covers the development of the Tandora Chrome Extension under Manifest V3: DOM extraction from LinkedIn profiles and posts, visible ContactOut and Apollo.io overlay extraction, manual copy-paste fallback parsing, editable review popup UX, keyboard shortcuts, and authenticated transmission to `http://127.0.0.1:8000/api/v1/captures`.

## When to Use

Read this skill before writing or modifying any extension code in `extension/`.

## Required Engineering Practices

### 1. Manifest V3 & Least-Privilege Permissions
- Request only `activeTab`, `scripting`, and `storage`.
- Narrowly scope host permissions to the local backend: `http://127.0.0.1:8000/*`.
- **Avoid `<all_urls>`** host permissions.
- Inject content scripts programmatically on user action (`chrome.scripting.executeScript`) rather than auto-injecting into every webpage.

```json
{
  "manifest_version": 3,
  "name": "Tandora Prospect Capture",
  "version": "1.0.0",
  "description": "Capture job opportunities, LinkedIn profiles/posts, and contact details into Tandora.",
  "permissions": ["activeTab", "scripting", "storage"],
  "host_permissions": ["http://127.0.0.1:8000/*"],
  "action": {
    "default_popup": "popup/popup.html",
    "default_title": "Capture Prospect (Alt+Shift+T)"
  },
  "background": {
    "service_worker": "background.js"
  },
  "commands": {
    "_execute_action": {
      "suggested_key": {
        "default": "Alt+Shift+T"
      },
      "description": "Open Tandora capture popup"
    }
  }
}
```

### 2. Supported Page Types & DOM Extractors

#### A. LinkedIn Individual Profiles
Extracts:
- `person.full_name`, `person.first_name`, `person.last_name`
- `person.headline`
- `person.current_company`
- `person.job_title`
- `person.location`
- `person.linkedin_url` (canonical profile URL)

#### B. LinkedIn Posts
Extracts:
- `post.author_name`
- `post.author_linkedin_url`
- `post.author_headline`
- `post.post_url`
- `post.text` (visible body / excerpt)
- `post.post_timestamp`
- `post.company_mentioned`

*Critical Distinction*: The author of a LinkedIn post is not necessarily the person whose profile is being viewed. Tandora captures the post author as a potential decision-maker while preserving the post text as context for the opportunity.

#### C. ContactOut & Apollo.io Overlays (Strictly Conditional)
- DOM extraction is strictly best-effort and conditional: closed shadow roots (`shadowRoot` mode `closed`), isolated extension interfaces, and sandboxed iframes can inherently prevent content scripts from accessing or traversing these third-party elements.
- When accessible in the active tab DOM, extract visible work/personal emails and phone numbers.
- Tag each extracted channel with its detected source: `ContactOut` or `Apollo`.

### 3. Compliance & Boundary Rules
- **Never** reverse-engineer ContactOut or Apollo private APIs.
- **Never** bypass paywalls, authentication, or technical access controls.
- **Never** crawl or scrape LinkedIn servers automatically.
- **Never** run automated profile-browsing or scraping loops.
- Extract data only upon explicit user action from the active tab.

### 4. Essential Manual Paste Fallback Form (Mandatory Core Feature)
Because third-party extensions frequently isolate their interfaces in closed shadow roots or sandboxed frames, DOM extraction must never be assumed to succeed. The manual paste fallback is an essential, first-class requirement:
- The popup prominently provides a **"Quick Paste / Manual Import"** interface.
- The user copies text from ContactOut, Apollo, or any external tool and pastes it into the form.
- Client-side heuristic parser extracts:
  - Emails using regex: `/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g`
  - Phone numbers using international/E.164 patterns.
  - Names, titles, and company names from surrounding text blocks.
- Extracted values automatically populate the editable review form before user submission.

### 5. Structured Capture Payload Schema

```json
{
  "capture_type": "linkedin_profile",
  "page_type": "linkedin_profile",
  "source_url": "https://www.linkedin.com/in/janedoe/",
  "source_title": "Jane Doe - VP of Engineering - Acme Corp | LinkedIn",
  "captured_at": "2026-11-21T13:00:00Z",
  "opportunity_type": "employment",
  "person": {
    "full_name": "Jane Doe",
    "first_name": "Jane",
    "last_name": "Doe",
    "linkedin_url": "https://www.linkedin.com/in/janedoe",
    "job_title": "VP of Engineering",
    "headline": "VP of Engineering at Acme Corp",
    "location": "San Francisco, CA"
  },
  "company": {
    "name": "Acme Corp",
    "website": "https://acme.com"
  },
  "emails": [
    {
      "address": "jane.doe@acme.com",
      "source": "Apollo",
      "source_url": "https://www.linkedin.com/in/janedoe/",
      "is_primary": true
    }
  ],
  "phone_numbers": [
    {
      "number": "+1-555-0199",
      "type": "direct",
      "source": "ContactOut",
      "source_url": "https://www.linkedin.com/in/janedoe/"
    }
  ],
  "post": null,
  "selected_text": "",
  "user_notes": "Met at Cloud Summit; hiring for Platform Team."
}
```

### 6. Review-Before-Submit Popup UX
1. On open, the popup executes extraction on the active tab and populates all fields.
2. The user sees:
   - Extracted Name, Title, Company, Location.
   - List of extracted email addresses with source tags.
   - List of extracted phone numbers with source tags.
   - Opportunity Type dropdown (`employment` vs `freelance_prospect`).
   - Notes field.
3. Every field is fully editable.
4. User clicks **"Capture Prospect"**.
5. Popup sends `POST http://127.0.0.1:8000/api/v1/captures` with header `X-Extension-Secret: <secret>`.
6. On success: displays confirmation with a direct link to open the prospect in the Local Web UI.

---

## Security Considerations

- The extension secret is stored in `chrome.storage.local`. It is never written to DOM or console.
- Network requests are strictly limited to `http://127.0.0.1:8000/*`.
- Third-party scripts are never executed in the extension context.
