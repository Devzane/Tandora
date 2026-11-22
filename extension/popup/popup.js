/**
 * Tandora Prospect Capture - Popup Controller
 * Manages extraction review, manual paste fallback, settings, and authenticated backend transmission.
 */

document.addEventListener("DOMContentLoaded", async () => {
  // DOM Elements - Tabs
  const tabReviewBtn = document.getElementById("tabReviewBtn");
  const tabPasteBtn = document.getElementById("tabPasteBtn");
  const tabSettingsBtn = document.getElementById("tabSettingsBtn");
  const viewReview = document.getElementById("viewReview");
  const viewPaste = document.getElementById("viewPaste");
  const viewSettings = document.getElementById("viewSettings");

  // DOM Elements - Alerts
  const successBanner = document.getElementById("successBanner");
  const successDetails = document.getElementById("successDetails");
  const viewLocalUiLink = document.getElementById("viewLocalUiLink");
  const dismissSuccessBtn = document.getElementById("dismissSuccessBtn");
  const duplicateBanner = document.getElementById("duplicateBanner");
  const errorBanner = document.getElementById("errorBanner");
  const errorDetails = document.getElementById("errorDetails");
  const retryBtn = document.getElementById("retryBtn");
  const pageTypeBadge = document.getElementById("pageTypeBadge");

  // DOM Elements - Form Fields
  const captureForm = document.getElementById("captureForm");
  const firstNameInput = document.getElementById("firstNameInput");
  const lastNameInput = document.getElementById("lastNameInput");
  const headlineInput = document.getElementById("headlineInput");
  const locationInput = document.getElementById("locationInput");
  const linkedinUrlInput = document.getElementById("linkedinUrlInput");

  const companyNameInput = document.getElementById("companyNameInput");
  const companyTypeSelect = document.getElementById("companyTypeSelect");
  const companyWebsiteInput = document.getElementById("companyWebsiteInput");

  const createOppCheckbox = document.getElementById("createOppCheckbox");
  const oppFields = document.getElementById("oppFields");
  const oppTitleInput = document.getElementById("oppTitleInput");
  const oppTypeSelect = document.getElementById("oppTypeSelect");

  const postSection = document.getElementById("postSection");
  const postAuthorNameInput = document.getElementById("postAuthorNameInput");
  const postTimestampInput = document.getElementById("postTimestampInput");
  const postTextInput = document.getElementById("postTextInput");

  const emailsList = document.getElementById("emailsList");
  const newEmailInput = document.getElementById("newEmailInput");
  const newEmailSourceSelect = document.getElementById("newEmailSourceSelect");
  const addEmailBtn = document.getElementById("addEmailBtn");

  const phonesList = document.getElementById("phonesList");
  const newPhoneInput = document.getElementById("newPhoneInput");
  const newPhoneSourceSelect = document.getElementById("newPhoneSourceSelect");
  const addPhoneBtn = document.getElementById("addPhoneBtn");

  const userNotesInput = document.getElementById("userNotesInput");
  const submitCaptureBtn = document.getElementById("submitCaptureBtn");
  const submitSpinner = document.getElementById("submitSpinner");
  const submitText = document.getElementById("submitText");

  // DOM Elements - Paste Fallback
  const pasteTextarea = document.getElementById("pasteTextarea");
  const pasteSourceSelect = document.getElementById("pasteSourceSelect");
  const parsePasteBtn = document.getElementById("parsePasteBtn");

  // DOM Elements - Settings
  const backendUrlInput = document.getElementById("backendUrlInput");
  const secretInput = document.getElementById("secretInput");
  const saveSettingsBtn = document.getElementById("saveSettingsBtn");
  const testConnBtn = document.getElementById("testConnBtn");
  const connStatus = document.getElementById("connStatus");

  // In-Memory State
  let currentExtraction = null;
  let currentEmails = [];
  let currentPhones = [];
  let storedConfig = {
    backendUrl: "http://127.0.0.1:8000",
    extensionSecret: "tandora-secure-local-extension-token",
  };

  // --- 1. Load Stored Configuration ---
  async function loadConfig() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["backendUrl", "extensionSecret"], (items) => {
        if (items.backendUrl) storedConfig.backendUrl = items.backendUrl;
        if (items.extensionSecret) storedConfig.extensionSecret = items.extensionSecret;
        backendUrlInput.value = storedConfig.backendUrl;
        secretInput.value = storedConfig.extensionSecret;
        resolve(storedConfig);
      });
    });
  }

  await loadConfig();

  // --- 2. Tab Navigation ---
  function switchTab(activeBtn, activeView) {
    [tabReviewBtn, tabPasteBtn, tabSettingsBtn].forEach((b) => b.classList.remove("active"));
    [viewReview, viewPaste, viewSettings].forEach((v) => v.classList.remove("active"));
    activeBtn.classList.add("active");
    activeView.classList.add("active");
  }

  tabReviewBtn.addEventListener("click", () => switchTab(tabReviewBtn, viewReview));
  tabPasteBtn.addEventListener("click", () => switchTab(tabPasteBtn, viewPaste));
  tabSettingsBtn.addEventListener("click", () => switchTab(tabSettingsBtn, viewSettings));

  // --- 3. Alert Helpers ---
  function clearAlerts() {
    successBanner.classList.add("hidden");
    duplicateBanner.classList.add("hidden");
    errorBanner.classList.add("hidden");
  }

  function showError(msg) {
    errorDetails.textContent = msg;
    errorBanner.classList.remove("hidden");
  }

  function showSuccess(msg, contactId, companyId, opportunityId, isDuplicate) {
    successDetails.textContent = msg;
    if (contactId) {
      viewLocalUiLink.href = `${storedConfig.backendUrl}/contacts/${contactId}`;
      viewLocalUiLink.textContent = "View Contact in Tandora";
    } else if (opportunityId) {
      viewLocalUiLink.href = `${storedConfig.backendUrl}/opportunities/${opportunityId}`;
      viewLocalUiLink.textContent = "View Opportunity in Tandora";
    } else if (companyId) {
      viewLocalUiLink.href = `${storedConfig.backendUrl}/organizations/${companyId}`;
      viewLocalUiLink.textContent = "View Organization in Tandora";
    } else {
      viewLocalUiLink.href = `${storedConfig.backendUrl}/`;
      viewLocalUiLink.textContent = "Open Tandora Dashboard";
    }
    successBanner.classList.remove("hidden");
    if (isDuplicate) {
      duplicateBanner.classList.remove("hidden");
    }
  }

  dismissSuccessBtn.addEventListener("click", () => successBanner.classList.add("hidden"));

  // Toggle Opportunity Fields
  createOppCheckbox.addEventListener("change", () => {
    oppFields.style.display = createOppCheckbox.checked ? "block" : "none";
  });

  // --- 4. Render Channel Lists ---
  function renderEmails() {
    emailsList.innerHTML = "";
    currentEmails.forEach((item, index) => {
      const div = document.createElement("div");
      div.className = "channel-item";
      div.innerHTML = `
        <span class="channel-val">${item.address}</span>
        <div>
          <span class="channel-tag">${item.source || "manual"}</span>
          <button type="button" class="channel-remove-btn" data-index="${index}">&times;</button>
        </div>
      `;
      div.querySelector(".channel-remove-btn").addEventListener("click", () => {
        currentEmails.splice(index, 1);
        renderEmails();
      });
      emailsList.appendChild(div);
    });
  }

  function renderPhones() {
    phonesList.innerHTML = "";
    currentPhones.forEach((item, index) => {
      const div = document.createElement("div");
      div.className = "channel-item";
      div.innerHTML = `
        <span class="channel-val">${item.number}</span>
        <div>
          <span class="channel-tag">${item.source || "manual"}</span>
          <button type="button" class="channel-remove-btn" data-index="${index}">&times;</button>
        </div>
      `;
      div.querySelector(".channel-remove-btn").addEventListener("click", () => {
        currentPhones.splice(index, 1);
        renderPhones();
      });
      phonesList.appendChild(div);
    });
  }

  addEmailBtn.addEventListener("click", () => {
    const val = newEmailInput.value.trim();
    if (val && val.includes("@")) {
      currentEmails.push({
        address: val.toLowerCase(),
        source: newEmailSourceSelect.value,
        is_primary: currentEmails.length === 0 ? 1 : 0,
      });
      newEmailInput.value = "";
      renderEmails();
    }
  });

  addPhoneBtn.addEventListener("click", () => {
    const val = newPhoneInput.value.trim();
    if (val) {
      currentPhones.push({
        number: val,
        type: "direct",
        source: newPhoneSourceSelect.value,
      });
      newPhoneInput.value = "";
      renderPhones();
    }
  });

  // --- 5. Populate Form from Extraction ---
  function populateForm(data) {
    currentExtraction = data;
    clearAlerts();

    // Badge
    const pageType = data.page_type || data.capture_type || "web";
    pageTypeBadge.textContent = pageType.replace("_", " ").toUpperCase();

    // Person
    if (data.person) {
      firstNameInput.value = data.person.first_name || "";
      lastNameInput.value = data.person.last_name || "";
      headlineInput.value = data.person.headline || "";
      locationInput.value = data.person.location || "";
      linkedinUrlInput.value = data.person.linkedin_url || "";
    }

    // Company
    if (data.company) {
      companyNameInput.value = data.company.name || "";
      companyTypeSelect.value = data.company.type || "employer";
      companyWebsiteInput.value = data.company.website || "";
    }

    // Opportunity
    if (data.opportunity) {
      createOppCheckbox.checked = true;
      oppFields.style.display = "block";
      oppTitleInput.value = data.opportunity.title || "";
      oppTypeSelect.value = data.opportunity.type || "employment";
    } else {
      createOppCheckbox.checked = false;
      oppFields.style.display = "none";
    }

    // Post Details
    if (data.post) {
      postSection.classList.remove("hidden");
      postAuthorNameInput.value = data.post.author_name || "";
      postTimestampInput.value = data.post.post_timestamp || "";
      postTextInput.value = data.post.post_text || "";
    } else {
      postSection.classList.add("hidden");
    }

    // Emails and Phones
    currentEmails = Array.isArray(data.emails) ? [...data.emails] : [];
    currentPhones = Array.isArray(data.phones) ? [...data.phones] : [];
    renderEmails();
    renderPhones();

    // Notes
    if (data.selected_text) {
      userNotesInput.value = `Selected excerpt: "${data.selected_text}"`;
    }
  }

  // --- 6. Active Tab Extraction via Content Script ---
  async function runTabExtraction() {
    clearAlerts();
    pageTypeBadge.textContent = "INSPECTING...";

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.id) {
        showError("No active browser tab found.");
        return;
      }

      if (tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) {
        pageTypeBadge.textContent = "LOCAL / INTERNAL";
        firstNameInput.value = "Internal Page";
        return;
      }

      // Execute content.js programmatically on user action
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"],
      });

      if (results && results[0] && results[0].result) {
        populateForm(results[0].result);
      } else {
        pageTypeBadge.textContent = "MANUAL MODE";
      }
    } catch (err) {
      console.warn("DOM extraction note:", err);
      pageTypeBadge.textContent = "MANUAL / FALLBACK";
      // Allow user to use manual form without error blocking
    }
  }

  // Run extraction on popup open
  runTabExtraction();

  // --- 7. Manual Copy-Paste Fallback Action ---
  parsePasteBtn.addEventListener("click", () => {
    const text = pasteTextarea.value.trim();
    if (!text) {
      alert("Please paste text from ContactOut, Apollo, or LinkedIn first.");
      return;
    }

    const defaultSource = pasteSourceSelect.value;
    const parsed = window.TandoraParser.parsePastedText(text, defaultSource);

    // Merge parsed items into review form
    if (parsed.firstName) firstNameInput.value = parsed.firstName;
    if (parsed.lastName) lastNameInput.value = parsed.lastName;
    if (parsed.headline) headlineInput.value = parsed.headline;
    if (parsed.company) companyNameInput.value = parsed.company;
    if (parsed.location) locationInput.value = parsed.location;
    if (parsed.linkedinUrl) linkedinUrlInput.value = parsed.linkedinUrl;

    if (parsed.emails && parsed.emails.length > 0) {
      currentEmails = [...currentEmails, ...parsed.emails];
      renderEmails();
    }

    if (parsed.phones && parsed.phones.length > 0) {
      currentPhones = [...currentPhones, ...parsed.phones];
      renderPhones();
    }

    // Switch back to review view
    switchTab(tabReviewBtn, viewReview);
  });

  // --- 8. Settings & Connection Testing ---
  saveSettingsBtn.addEventListener("click", () => {
    const backendUrl = backendUrlInput.value.trim().replace(/\/+$/, "");
    const extensionSecret = secretInput.value.trim();

    chrome.storage.local.set({ backendUrl, extensionSecret }, () => {
      storedConfig.backendUrl = backendUrl;
      storedConfig.extensionSecret = extensionSecret;
      connStatus.textContent = "Settings saved successfully.";
      connStatus.style.color = "var(--success-color)";
      setTimeout(() => (connStatus.textContent = ""), 3000);
    });
  });

  testConnBtn.addEventListener("click", async () => {
    connStatus.textContent = "Testing connection...";
    connStatus.style.color = "var(--text-muted)";
    try {
      const res = await fetch(`${backendUrlInput.value.trim().replace(/\/+$/, "")}/health`, {
        method: "GET",
      });
      if (res.ok) {
        connStatus.textContent = "✓ Connected to Tandora Hub (127.0.0.1:8000)";
        connStatus.style.color = "var(--success-color)";
      } else {
        connStatus.textContent = `Server responded with HTTP ${res.status}`;
        connStatus.style.color = "var(--danger-color)";
      }
    } catch (err) {
      connStatus.textContent = "✕ Could not connect to local Tandora server. Is it running?";
      connStatus.style.color = "var(--danger-color)";
    }
  });

  // --- 9. Form Submission to Local Backend ---
  async function submitCapture() {
    clearAlerts();

    const firstName = firstNameInput.value.trim();
    const companyName = companyNameInput.value.trim();

    if (!firstName && !companyName) {
      showError("Please provide at least a Prospect First Name or Company Name.");
      return;
    }

    // Loading State
    submitSpinner.classList.remove("hidden");
    submitText.textContent = "Saving to Tandora...";
    submitCaptureBtn.disabled = true;

    // Build Payload
    const captureType = currentExtraction?.capture_type || "extension_dom";
    const pageType = currentExtraction?.page_type || "profile";
    const sourceUrl = currentExtraction?.source_url || linkedinUrlInput.value.trim() || "http://localhost";

    const payload = {
      capture_type: captureType,
      source_type: "extension_dom",
      page_type: pageType,
      source_url: sourceUrl,
      source_title: currentExtraction?.source_title || null,
      selected_text: currentExtraction?.selected_text || null,
      user_notes: userNotesInput.value.trim() || null,
      captured_at: new Date().toISOString(),
      raw_payload: currentExtraction || { captured_via: "tandora_extension" },
    };

    // Attach Company
    if (companyName) {
      payload.company = {
        name: companyName,
        type: companyTypeSelect.value,
        website: companyWebsiteInput.value.trim() || null,
        source_url: sourceUrl,
      };
    }

    // Attach Opportunity
    if (createOppCheckbox.checked && oppTitleInput.value.trim()) {
      payload.opportunity = {
        title: oppTitleInput.value.trim(),
        type: oppTypeSelect.value,
        source_url: sourceUrl,
      };
    }

    // Attach Contact
    if (firstName) {
      payload.contact = {
        first_name: firstName,
        last_name: lastNameInput.value.trim() || null,
        headline: headlineInput.value.trim() || null,
        location: locationInput.value.trim() || null,
        linkedin_url: linkedinUrlInput.value.trim() || null,
        notes: userNotesInput.value.trim() || null,
        roles: headlineInput.value.trim() ? [{ role: headlineInput.value.trim() }] : [],
        emails: currentEmails,
        phones: currentPhones,
      };
    }

    // Attach Post if present
    if (postAuthorNameInput.value.trim()) {
      payload.post = {
        author_name: postAuthorNameInput.value.trim(),
        post_url: sourceUrl,
        post_text: postTextInput.value.trim() || "Captured post excerpt",
        post_timestamp: postTimestampInput.value.trim() || null,
        company_mentioned: companyName || null,
        create_author_contact: true,
      };
    }

    try {
      const endpoint = `${storedConfig.backendUrl}/api/v1/captures/`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Extension-Secret": storedConfig.extensionSecret,
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (response.status === 201) {
        const isDuplicate = data.duplicate_flag === 1;
        showSuccess(data.message, data.contact_id, data.company_id, data.opportunity_id, isDuplicate);
      } else if (response.status === 401) {
        showError("Authentication rejected: Invalid or missing X-Extension-Secret. Please verify in Settings.");
      } else {
        showError(data.detail || `Server returned error (${response.status})`);
      }
    } catch (err) {
      showError(`Connection error: Failed to reach ${storedConfig.backendUrl}. Is Tandora backend running?`);
    } finally {
      submitSpinner.classList.add("hidden");
      submitText.textContent = "Capture to Tandora";
      submitCaptureBtn.disabled = false;
    }
  }

  captureForm.addEventListener("submit", (e) => {
    e.preventDefault();
    submitCapture();
  });

  retryBtn.addEventListener("click", () => {
    clearAlerts();
    submitCapture();
  });
});
