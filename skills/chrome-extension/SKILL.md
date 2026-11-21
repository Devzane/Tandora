---
name: chrome-extension
description: Chrome Extension Manifest V3 development for Tandora — content scripts, service workers, popup UI, keyboard shortcuts, and secure backend communication.
risk: low
source: project
date_added: '2026-11-21'
---

# Chrome Extension Skill — Tandora

## Purpose

This skill covers the Tandora Chrome Extension: Manifest V3 structure, capturing page data, the popup UI, the background service worker, keyboard shortcuts, and authenticated communication with the local FastAPI backend.

## When to Use

Read this skill before writing any extension code in `extension/`.

## Required Engineering Practices

### Manifest V3 Structure

```json
{
  "manifest_version": 3,
  "name": "Tandora Capture",
  "version": "1.0.0",
  "description": "Capture job opportunities and company leads into Tandora.",
  "permissions": ["activeTab", "scripting", "storage"],
  "host_permissions": ["http://127.0.0.1:8000/*"],
  "action": {
    "default_popup": "popup/popup.html",
    "default_title": "Tandora Capture"
  },
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ],
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

### Background Service Worker

- The service worker (`background.js`) must not use Manifest V2 `background page` patterns.
- It may not use `chrome.extension.getBackgroundPage()`.
- Use `chrome.runtime.onMessage` for communication with popup and content scripts.
- Do not store state in service worker variables (they are cleared when the worker goes idle). Use `chrome.storage.local` or `chrome.storage.session` instead.

### Content Script

The content script (`content.js`) is injected into the active page. It may:
- Read `document.title`, `window.location.href`, and `window.getSelection().toString()`.
- Send this data to the popup via `chrome.runtime.sendMessage`.

It must not:
- Make direct calls to the FastAPI backend (this is the popup's responsibility).
- Access the DOM in ways that break the host page.

### Popup

```javascript
// popup/popup.js
document.addEventListener('DOMContentLoaded', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  // Get selected text from content script
  const response = await chrome.tabs.sendMessage(tab.id, { action: 'getSelection' });
  
  document.getElementById('url').value = tab.url;
  document.getElementById('title').value = tab.title;
  document.getElementById('selection').value = response?.selection || '';
});

document.getElementById('submit-btn').addEventListener('click', async () => {
  const secret = await getStoredSecret();
  const payload = buildPayload();
  
  const res = await fetch('http://127.0.0.1:8000/api/v1/captures', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Extension-Secret': secret
    },
    body: JSON.stringify(payload)
  });
  
  if (res.ok) {
    showSuccess();
  } else {
    showError(await res.json());
  }
});
```

### Storing the Extension Secret

The extension secret must be stored in `chrome.storage.local`, not hardcoded in JavaScript source:

```javascript
// Set during installation/setup
await chrome.storage.local.set({ extensionSecret: 'value-from-user-setup' });

// Read before each request
async function getStoredSecret() {
  const { extensionSecret } = await chrome.storage.local.get('extensionSecret');
  return extensionSecret;
}
```

### Permissions

Request only the permissions actually needed:
- `activeTab`: Read the current tab's URL and title.
- `scripting`: Inject content scripts.
- `storage`: Store the extension secret.
- `host_permissions: ["http://127.0.0.1:8000/*"]`: Allow fetch to the local backend.

Do not request `<all_urls>` host permissions unless required.

## Implementation Guidelines

1. Keep all backend communication in the popup script. Never call the backend from content scripts.
2. Display clear success and error states in the popup UI.
3. Show the user what data was captured before submission.
4. Allow editing of captured fields (company name, opportunity title, notes) before submission.
5. After successful submission, show the created opportunity ID and a link/confirmation.

## Common Mistakes

- Using Manifest V2 patterns (`background.persistent`, `browser_action`). → Use MV3 equivalents.
- Storing the secret in `const SECRET = "..."` in JavaScript. → Use `chrome.storage.local`.
- Making fetch calls to `localhost` instead of `127.0.0.1`. → Chrome treats these differently for host permissions.
- Forgetting the `host_permissions` for `http://127.0.0.1:8000/*`. → Extension will be blocked from calling the backend.
- Opening too many tabs or windows from the popup. → Popup should close after submission.

## Security Considerations

- The extension secret is stored in `chrome.storage.local`. It is accessible to the extension only, not to web pages.
- Never log the secret to the browser console.
- The backend must validate the secret on every request from the extension.
- The extension must only communicate with `127.0.0.1:8000`. Do not add other origins.

## Testing Requirements

- Load the extension as "unpacked" in Chrome and verify:
  - The popup opens from the toolbar button.
  - The keyboard shortcut opens the popup.
  - The URL and title are pre-populated correctly.
  - Submission succeeds and shows a success message.
  - Submission without the secret configured shows a clear error.
- Test the backend `captures` endpoint independently with `curl` to verify secret validation.

## Project-Specific Constraints

- Backend URL is always `http://127.0.0.1:8000`. It is not configurable in the extension (backend is always local).
- The extension does not store captured data locally. All data goes directly to the backend.
- The extension supports one capture type at a time (employment opportunity or freelance prospect), selected via a dropdown in the popup.
