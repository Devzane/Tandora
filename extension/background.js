/**
 * Tandora Chrome Extension - Background Service Worker (Manifest V3)
 * Manages extension lifecycle and message passing.
 */

chrome.runtime.onInstalled.addListener((details) => {
  console.log("Tandora Prospect Capture extension installed/updated:", details.reason);
  // Initialize default backend URL in chrome.storage.local if not already set.
  // The secret is never hardcoded in source code; user configures it via the Settings tab.
  chrome.storage.local.get(["backendUrl"], (res) => {
    if (!res.backendUrl) {
      chrome.storage.local.set({ backendUrl: "http://127.0.0.1:8000" }, () => {
        console.log("Tandora storage initialized with local default backendUrl.");
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
