/**
 * Tandora Prospect Capture - Heuristic Text Parser
 * Used for Manual Copy-and-Paste Fallback from ContactOut, Apollo, LinkedIn, and external sources.
 */

(function (root, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    module.exports = factory();
  } else {
    root.TandoraParser = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  const EMAIL_REGEX = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

  // Matches phone numbers including international (+1 ..., +44 ...), dashes, dots, spaces, parenthesized area codes
  const PHONE_REGEX = /(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,4})?/g;

  /**
   * Cleans text lines and removes noise.
   */
  function cleanLines(rawText) {
    if (!rawText) return [];
    return rawText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  }

  /**
   * Extracts distinct valid email addresses from text.
   */
  function extractEmails(text, defaultSource = "manual") {
    if (!text) return [];
    const matches = text.match(EMAIL_REGEX) || [];
    const seen = new Set();
    const results = [];

    for (const raw of matches) {
      const email = raw.trim().toLowerCase();
      // Exclude obvious image/file/dummy artifacts
      if (email.endsWith(".png") || email.endsWith(".jpg") || email.endsWith(".svg")) continue;
      if (!seen.has(email)) {
        seen.add(email);
        results.push({
          address: email,
          source: defaultSource,
          is_primary: results.length === 0 ? 1 : 0,
        });
      }
    }
    return results;
  }

  /**
   * Extracts distinct valid phone numbers from text.
   */
  function extractPhones(text, defaultSource = "manual") {
    if (!text) return [];
    const matches = text.match(PHONE_REGEX) || [];
    const seen = new Set();
    const results = [];

    for (const raw of matches) {
      const trimmed = raw.trim();
      const digitsOnly = trimmed.replace(/\D/g, "");
      // Valid phone numbers generally have between 7 and 15 digits
      if (digitsOnly.length >= 7 && digitsOnly.length <= 15) {
        if (!seen.has(trimmed)) {
          seen.add(trimmed);
          results.push({
            number: trimmed,
            type: "direct",
            source: defaultSource,
          });
        }
      }
    }
    return results;
  }

  /**
   * Parses unstructured copied text block into structured prospect fields.
   */
  function parsePastedText(text, fallbackSource = "extension_manual_paste") {
    const lines = cleanLines(text);
    const emails = extractEmails(text, fallbackSource);
    const phones = extractPhones(text, fallbackSource);

    let fullName = "";
    let firstName = "";
    let lastName = "";
    let headline = "";
    let company = "";
    let location = "";
    let linkedinUrl = "";

    // Check for LinkedIn URL inside text
    const linkedinMatch = text.match(/https?:\/\/(?:[a-z]{2,3}\.)?linkedin\.com\/(?:in|company)\/[a-zA-Z0-9_-]+/i);
    if (linkedinMatch) {
      linkedinUrl = linkedinMatch[0];
    }

    // Identify candidate name, headline, and company from non-email, non-phone lines
    const textLines = lines.filter((line) => {
      // Exclude lines that are purely emails, phones, or URLs
      if (EMAIL_REGEX.test(line)) return false;
      if (line.match(/^https?:\/\//i)) return false;
      const digitsOnly = line.replace(/\D/g, "");
      if (digitsOnly.length >= 7 && digitsOnly.length <= 15 && line.length < 30) return false;
      // Exclude common noise labels
      const lower = line.toLowerCase();
      if (
        lower === "email" ||
        lower === "phone" ||
        lower === "contact info" ||
        lower === "contactout" ||
        lower === "apollo" ||
        lower === "apollo.io" ||
        lower === "view profile" ||
        lower === "connect" ||
        lower === "message" ||
        lower === "more" ||
        lower === "save"
      ) {
        return false;
      }
      return true;
    });

    if (textLines.length > 0) {
      // First clean line is typically the Person's Name
      const candidateName = textLines[0].replace(/^(name|contact):\s*/i, "").trim();
      const nameParts = candidateName.split(/\s+/);
      if (nameParts.length >= 1 && candidateName.length < 60) {
        fullName = candidateName;
        firstName = nameParts[0];
        lastName = nameParts.slice(1).join(" ");
      }
    }

    if (textLines.length > 1) {
      // Second line is typically Headline or Job Title
      const candidateHeadline = textLines[1].replace(/^(title|headline|role):\s*/i, "").trim();
      headline = candidateHeadline;

      // Check if line contains "at [Company]" or "@ [Company]"
      const atCompanyMatch = candidateHeadline.match(/(?:at|@)\s+([A-Za-z0-9&.,\s'-]+)$/i);
      if (atCompanyMatch) {
        company = atCompanyMatch[1].trim();
      }
    }

    if (!company && textLines.length > 2) {
      // Third line is frequently Company Name or Location
      const candidateCompany = textLines[2].replace(/^(company|org|organization):\s*/i, "").trim();
      if (
        !candidateCompany.toLowerCase().includes("united states") &&
        !candidateCompany.toLowerCase().includes("area") &&
        !candidateCompany.toLowerCase().includes("city") &&
        candidateCompany.length < 80
      ) {
        company = candidateCompany;
      } else {
        location = candidateCompany;
      }
    }

    if (!location && textLines.length > 3) {
      const candidateLoc = textLines[3].replace(/^(location|city|country):\s*/i, "").trim();
      if (candidateLoc.length < 80) {
        location = candidateLoc;
      }
    }

    return {
      fullName,
      firstName: firstName || (fullName ? fullName : "Unknown"),
      lastName,
      headline,
      company,
      location,
      linkedinUrl,
      emails,
      phones,
      rawText: text,
    };
  }

  return {
    EMAIL_REGEX,
    PHONE_REGEX,
    extractEmails,
    extractPhones,
    parsePastedText,
  };
});
