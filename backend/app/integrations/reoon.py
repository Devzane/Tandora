"""Reoon Email Verifier API client."""

import logging
import re
from typing import Any
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

REOON_API_URL = "https://emailverifier.reoon.com/api/v1/verify"


class ReoonAPIError(Exception):
    """Raised when Reoon API request fails or returns an error response."""
    pass


def _sanitize_provider_reason(reason: Any, api_key: str | None = None) -> str:
    """Sanitize provider error strings to prevent leaking credentials, URLs, or query parameters."""
    if not reason:
        return "Unknown API error"
    text = str(reason).strip()
    if api_key and api_key in text:
        text = text.replace(api_key, "[REDACTED]")
    text = re.sub(r"(?i)(key|token|secret|password|api[_-]?key)=[^\s&'\"]+", r"\1=[REDACTED]", text)
    text = re.sub(r"https?://[^\s'\"]+", "[REDACTED_URL]", text)
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    text = " ".join(text.split())
    return text[:200]


class ReoonClient:
    """Client for interacting with the Reoon Email Verifier API."""

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.validate_reoon_credentials()
        self.timeout = timeout if timeout is not None else settings.reoon_timeout_seconds

    def verify(self, email_address: str) -> dict[str, Any]:
        """Verify an email address in deep 'power' mode via Reoon API.

        Raises ReoonAPIError on network errors, timeouts, HTTP errors, or Reoon API failure status.
        Ensures credentials and sensitive URL query parameters are never logged or exposed in exceptions.
        """
        data: Any = None
        transport_error: ReoonAPIError | None = None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    REOON_API_URL,
                    params={
                        "email": email_address,
                        "key": self.api_key,
                        "mode": "power",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            logger.error("Reoon API request timed out after %.1fs in Power Mode", self.timeout)
            transport_error = ReoonAPIError(f"Reoon API request timed out after {self.timeout}s in Power Mode")
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error("Reoon API request failed with HTTP status %d", status_code)
            transport_error = ReoonAPIError(f"Reoon API returned HTTP {status_code}")
        except httpx.RequestError as e:
            error_cls = type(e).__name__
            logger.error("Reoon API network/connection error: %s", error_cls)
            transport_error = ReoonAPIError(f"Could not connect to Reoon API: {error_cls}")
        except Exception as e:
            error_cls = type(e).__name__
            logger.error("Unexpected error calling Reoon API: %s", error_cls)
            transport_error = ReoonAPIError(f"Unexpected Reoon API error: {error_cls}")

        # Raising outside the except block detaches the underlying httpx exception from __context__
        if transport_error is not None:
            raise transport_error from None

        if not isinstance(data, dict):
            raise ReoonAPIError(f"Malformed response from Reoon API: expected JSON object, got {type(data).__name__}")

        # Check for Reoon API-level error responses: {"status": "error", "reason": "..."}
        if data.get("status") == "error":
            raw_reason = data.get("reason", "Unknown API error")
            reason = _sanitize_provider_reason(raw_reason, api_key=self.api_key)
            logger.error("Reoon API returned error status: %s", reason)
            raise ReoonAPIError(f"Reoon API error: {reason}")

        return data
