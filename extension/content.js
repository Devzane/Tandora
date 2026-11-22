/**
 * Tandora Prospect Capture - DOM Extractor Content Script
 * Extracts structured prospect data from LinkedIn profiles, company pages,
 * job listings, posts, and accessible third-party overlays (ContactOut/Apollo).
 */

(function () {
  /**
   * Cleans and canonicalizes a LinkedIn URL by removing tracking query parameters and trailing slashes.
   */
  function cleanLinkedInUrl(url) {
    if (!url) return "";
    try {
      const u = new URL(url);
      return `${u.origin}${u.pathname}`.replace(/\/+$/, "");
    } catch (e) {
      return url.split("?")[0].replace(/\/+$/, "");
    }
  }

  /**
   * Helper to query text safely from selector.
   */
  function queryText(selectors, root = document) {
    if (!Array.isArray(selectors)) selectors = [selectors];
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      if (el && el.textContent) {
        const txt = el.textContent.trim();
        if (txt) return txt;
      }
    }
    return "";
  }

  /**
   * Detects the specific page type based on URL and DOM markers.
   */
  function detectPageType() {
    const href = window.location.href.toLowerCase();
    if (href.includes("linkedin.com/in/")) {
      return "linkedin_profile";
    }
    if (href.includes("linkedin.com/company/")) {
      return "linkedin_company";
    }
    if (href.includes("linkedin.com/jobs/view/") || (href.includes("linkedin.com/jobs/") && document.querySelector(".job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title"))) {
      return "job_listing";
    }
    if (href.includes("linkedin.com/feed/update/") || href.includes("linkedin.com/posts/")) {
      return "linkedin_post";
    }
    return "generic_web";
  }

  /**
   * Extracts data from a LinkedIn Individual Profile.
   */
  function extractLinkedInProfile() {
    // Selectors for Profile Name
    const nameSelectors = [
      "h1.text-heading-xlarge",
      "h1.inline.t-24",
      ".pv-top-card--list h1",
      "main section:first-of-type h1",
      ".ph5 h1",
    ];
    const fullName = queryText(nameSelectors);
    const parts = fullName ? fullName.split(/\s+/) : [];
    const firstName = parts[0] || "";
    const lastName = parts.length > 1 ? parts.slice(1).join(" ") : "";

    // Headline
    const headlineSelectors = [
      ".text-body-medium.break-words",
      ".pv-top-card--list-bullet .text-body-medium",
      "div[data-generated-suggestion-target]",
      ".ph5 .text-body-medium",
    ];
    const headline = queryText(headlineSelectors);

    // Current Company
    const companySelectors = [
      "button[aria-label*='Current company']",
      "div.pv-text-details__right-panel .inline-show-more-text",
      "div.pv-text-details__right-panel span",
      ".pv-top-card--experience-list-item",
      "#experience ~ div ul li:first-child .t-bold span",
    ];
    let companyName = queryText(companySelectors);
    // Fallback: look for "at [Company]" in headline
    if (!companyName && headline) {
      const match = headline.match(/(?:at|@)\s+([A-Za-z0-9&.,\s'-]+)$/i);
      if (match) companyName = match[1].trim();
    }

    // Location
    const locationSelectors = [
      ".text-body-small.inline.t-black--light.break-words",
      ".pv-top-card--list-bullet > li:first-child",
      ".ph5 .text-body-small.inline",
    ];
    const location = queryText(locationSelectors);

    // Profile URL
    const linkedinUrl = cleanLinkedInUrl(window.location.href);

    return {
      person: {
        full_name: fullName,
        first_name: firstName || (fullName ? fullName : "Unknown"),
        last_name: lastName || null,
        headline: headline || null,
        job_title: headline || null,
        location: location || null,
        linkedin_url: linkedinUrl,
      },
      company: companyName
        ? {
            name: companyName,
            type: "employer",
            source_url: linkedinUrl,
          }
        : null,
      opportunity: null,
      post: null,
    };
  }

  /**
   * Extracts data from a LinkedIn Company Page.
   */
  function extractLinkedInCompany() {
    const titleSelectors = [
      "h1.org-top-card-summary__title",
      "h1.inline",
      ".org-top-card-primary-content h1",
      "main h1",
    ];
    const companyName = queryText(titleSelectors);

    const taglineSelectors = [
      ".org-top-card-summary__tagline",
      ".org-top-card-summary-info-list",
      "p.break-words",
    ];
    const description = queryText(taglineSelectors);

    // Look for website link
    let website = null;
    const websiteLink = document.querySelector("a[data-field='topcard_website'], a[href*='//'][data-control-name='topcard_website'], .org-top-card-primary-actions__inner a[href^='http']");
    if (websiteLink && websiteLink.href) {
      website = websiteLink.href;
    }

    const infoList = queryText(".org-top-card-summary-info-list");

    return {
      person: null,
      company: {
        name: companyName || document.title.replace(/\|.*LinkedIn/i, "").trim(),
        website: website,
        industry: infoList || null,
        description: description || null,
        type: "employer",
        source_url: cleanLinkedInUrl(window.location.href),
      },
      opportunity: null,
      post: null,
    };
  }

  /**
   * Extracts data from a LinkedIn Job Listing.
   */
  function extractLinkedInJob() {
    const jobTitleSelectors = [
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      "h1.t-24",
      "h1",
    ];
    const jobTitle = queryText(jobTitleSelectors);

    const companySelectors = [
      ".job-details-jobs-unified-top-card__company-name a",
      ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name a",
      ".jobs-unified-top-card__company-name",
    ];
    const companyName = queryText(companySelectors);

    const locationSelectors = [
      ".job-details-jobs-unified-top-card__bullet",
      ".jobs-unified-top-card__bullet",
      ".job-details-jobs-unified-top-card__workplace-type",
    ];
    const location = queryText(locationSelectors);

    const descSelectors = [
      "#job-details",
      ".jobs-box__html-content",
      ".jobs-description__content",
    ];
    const fullDesc = queryText(descSelectors);
    const descExcerpt = fullDesc ? fullDesc.substring(0, 1000) : "";

    const jobUrl = cleanLinkedInUrl(window.location.href);

    return {
      person: null,
      company: {
        name: companyName || "Unknown Company",
        type: "employer",
        source_url: jobUrl,
      },
      opportunity: {
        title: jobTitle || "Open Role",
        description: descExcerpt,
        type: "employment",
        source_url: jobUrl,
      },
      post: null,
    };
  }

  /**
   * Extracts data from a LinkedIn Post.
   */
  function extractLinkedInPost() {
    // Post Author
    const authorSelectors = [
      ".update-components-actor__name span[dir='ltr']",
      ".update-components-actor__name span span",
      ".update-components-actor__name",
      ".feed-shared-actor__name",
    ];
    const authorName = queryText(authorSelectors);

    // Author Headline
    const authorHeadlineSelectors = [
      ".update-components-actor__description",
      ".feed-shared-actor__description",
    ];
    const authorHeadline = queryText(authorHeadlineSelectors);

    // Author Profile URL
    let authorUrl = "";
    const authorLinkEl = document.querySelector(".update-components-actor__container-link, a.update-components-actor__image, .feed-shared-actor__container-link");
    if (authorLinkEl && authorLinkEl.href) {
      authorUrl = cleanLinkedInUrl(authorLinkEl.href);
    }

    // Post Text Content
    const postBodySelectors = [
      ".update-components-update-v2__commentary",
      ".feed-shared-update-v2__description",
      ".feed-shared-text",
      ".update-components-text",
    ];
    const postText = queryText(postBodySelectors);

    // Post Timestamp
    const timeSelectors = [
      ".update-components-actor__sub-description",
      ".feed-shared-actor__sub-description",
    ];
    const postTimestamp = queryText(timeSelectors);

    const postUrl = cleanLinkedInUrl(window.location.href);

    return {
      person: null,
      company: null,
      opportunity: {
        title: `Hiring lead from ${authorName || "LinkedIn post"}`,
        description: postText ? postText.substring(0, 500) : "",
        type: "employment",
        source_url: postUrl,
      },
      post: {
        author_name: authorName || "Post Author",
        author_linkedin_url: authorUrl || null,
        author_headline: authorHeadline || null,
        post_url: postUrl,
        post_text: postText || "LinkedIn post excerpt",
        post_timestamp: postTimestamp || null,
        company_mentioned: null,
        create_author_contact: true,
      },
    };
  }

  /**
   * Conditionally checks for visible ContactOut or Apollo overlays in accessible DOM.
   * Note: strictly best-effort and conditional; closed shadow roots are not traversed.
   */
  function extractOverlays() {
    const emails = [];
    const phones = [];
    let overlayFound = false;

    // ContactOut Light DOM check
    const contactOutRoots = document.querySelectorAll(
      "#contactout-container, .contactout-container, [id*='contactout'], [class*='contactout']"
    );
    contactOutRoots.forEach((root) => {
      overlayFound = true;
      const text = root.innerText || root.textContent || "";
      const emailMatches = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [];
      emailMatches.forEach((em) => {
        emails.push({
          address: em.toLowerCase().trim(),
          source: "ContactOut",
          is_primary: emails.length === 0 ? 1 : 0,
        });
      });
      const phoneMatches = text.match(/(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}/g) || [];
      phoneMatches.forEach((ph) => {
        const digits = ph.replace(/\D/g, "");
        if (digits.length >= 7 && digits.length <= 15) {
          phones.push({
            number: ph.trim(),
            type: "direct",
            source: "ContactOut",
          });
        }
      });
    });

    // Apollo Light DOM check
    const apolloRoots = document.querySelectorAll(
      "#apollo-extension-root, .apollo-extension-container, [id*='apollo-extension'], [class*='apollo-extension']"
    );
    apolloRoots.forEach((root) => {
      overlayFound = true;
      const text = root.innerText || root.textContent || "";
      const emailMatches = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [];
      emailMatches.forEach((em) => {
        emails.push({
          address: em.toLowerCase().trim(),
          source: "Apollo",
          is_primary: emails.length === 0 ? 1 : 0,
        });
      });
      const phoneMatches = text.match(/(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}/g) || [];
      phoneMatches.forEach((ph) => {
        const digits = ph.replace(/\D/g, "");
        if (digits.length >= 7 && digits.length <= 15) {
          phones.push({
            number: ph.trim(),
            type: "direct",
            source: "Apollo",
          });
        }
      });
    });

    return { emails, phones, overlayFound };
  }

  /**
   * Main capture extraction entry point called by extension popup.
   */
  function captureActivePage() {
    const pageType = detectPageType();
    let extracted = {
      person: null,
      company: null,
      opportunity: null,
      post: null,
    };

    if (pageType === "linkedin_profile") {
      extracted = extractLinkedInProfile();
    } else if (pageType === "linkedin_company") {
      extracted = extractLinkedInCompany();
    } else if (pageType === "job_listing") {
      extracted = extractLinkedInJob();
    } else if (pageType === "linkedin_post") {
      extracted = extractLinkedInPost();
    } else {
      // Generic web page
      extracted.company = {
        name: document.title.split(/[-|]/)[0].trim() || "Web Prospect",
        type: "employer",
        source_url: window.location.href,
      };
    }

    // Best-effort check for overlays
    const overlays = extractOverlays();
    const emails = overlays.emails;
    const phones = overlays.phones;

    // Selected text (if user highlighted text on page)
    const selectedText = window.getSelection() ? window.getSelection().toString().trim() : "";

    return {
      success: true,
      capture_type: pageType,
      page_type: pageType,
      source_url: cleanLinkedInUrl(window.location.href),
      source_title: document.title || "",
      selected_text: selectedText || null,
      person: extracted.person,
      company: extracted.company,
      opportunity: extracted.opportunity,
      post: extracted.post,
      emails: emails,
      phones: phones,
      overlay_found: overlays.overlayFound,
      captured_at: new Date().toISOString(),
    };
  }

  // Execute and return data directly when invoked via chrome.scripting.executeScript
  return captureActivePage();
})();
