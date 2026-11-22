/**
 * Tandora Chrome Extension - Background Service Worker (Manifest V3)
 * Manages extension lifecycle and message passing.
 */

chrome.runtime.onInstalled.addListener((details) => {
  console.log("Tandora Prospect Capture extension installed/updated:", details.reason);
  // Initialize default configuration in chrome.storage.local if not already set
  chrome.storage.local.get(["backendUrl", "extensionSecret"], (res) => {
    const defaults = {};
    if (!res.backendUrl) {
      defaults.backendUrl = "http://127.0.0.1:8000";
    }
    if (!res.extensionSecret) {
      defaults.extensionSecret = "tandora-secure-local-extension-token";
    }
    if (Object.keys(defaults).length > 0) {
      chrome.storage.local.set(defaults, () => {
        console.log("Tandora storage initialized with local defaults.");
      });
    }
  });
});

// Listen for messages from popup or content script if needed
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "ping") {
    sendResponse({ status: "ok" });
  }
  return true;
});
