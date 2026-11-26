"""Google Gemini REST API Integration."""

import logging
import re
from typing import Any
import httpx

from app.config import get_settings
from app.providers.llm_interface import DraftResult, LLMGenerationError

logger = logging.getLogger(__name__)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _sanitize_provider_message(msg: Any, api_key: str | None = None) -> str:
    """Sanitize provider error strings to prevent leaking credentials or internal URLs."""
    if not msg:
        return "Unknown error"
    text = str(msg).strip()
    if api_key and api_key in text:
        text = text.replace(api_key, "[REDACTED]")
    text = re.sub(r"(?i)(key|token|secret|password|api[_-]?key)=[^\s&'\"]+", r"\1=[REDACTED]", text)
    text = re.sub(r"https?://[^\s'\"]+", "[REDACTED_URL]", text)
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    text = " ".join(text.split())
    return text[:200]


class GeminiProvider:
    """Client for generating text via Google Gemini REST API.

    Uses the official REST generateContent endpoint with header-based
    authentication (x-goog-api-key) to guarantee keys never appear in URLs.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.validate_gemini_credentials()
        self.model = model or settings.gemini_model
        self.timeout = timeout if timeout is not None else settings.llm_timeout_seconds

    @property
    def endpoint_url(self) -> str:
        """Return the target REST generateContent URL."""
        return f"{GEMINI_API_BASE_URL}/{self.model}:generateContent"

    def generate(self, prompt: str) -> DraftResult:
        """Generate text from a prompt using Google Gemini REST API.

        Raises:
            LLMGenerationError: On network errors, timeouts, HTTP errors, or malformed responses.
        """
        if not prompt or not prompt.strip():
            raise LLMGenerationError("Prompt must not be empty.")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        data: Any = None
        transport_error: LLMGenerationError | None = None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.endpoint_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            logger.error("Gemini API request timed out after %.1fs", self.timeout)
            transport_error = LLMGenerationError(f"Gemini API request timed out after {self.timeout}s")
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error("Gemini API request failed with HTTP status %d", status_code)
            detail = ""
            try:
                raw_text = e.response.text
                if raw_text:
                    sanitized_detail = _sanitize_provider_message(raw_text, api_key=self.api_key)
                    detail = f": {sanitized_detail}"
            except Exception:
                pass
            transport_error = LLMGenerationError(f"Gemini API returned HTTP {status_code}{detail}")
        except httpx.RequestError as e:
            error_cls = type(e).__name__
            logger.error("Gemini API connection error: %s", error_cls)
            transport_error = LLMGenerationError(f"Could not connect to Gemini API: {error_cls}")
        except Exception as e:
            error_cls = type(e).__name__
            logger.error("Unexpected error calling Gemini API: %s", error_cls)
            transport_error = LLMGenerationError(f"Unexpected Gemini API error: {error_cls}")

        # Raising outside the except block detaches the underlying httpx exception from __context__
        if transport_error is not None:
            raise transport_error from None

        if not isinstance(data, dict):
            raise LLMGenerationError(
                f"Malformed response from Gemini API: expected JSON object, got {type(data).__name__}"
            )

        # Handle provider-reported errors in JSON response
        if "error" in data:
            error_obj = data["error"]
            raw_msg = error_obj.get("message", "Unknown error") if isinstance(error_obj, dict) else str(error_obj)
            sanitized_msg = _sanitize_provider_message(raw_msg, api_key=self.api_key)
            logger.error("Gemini API returned provider error: %s", sanitized_msg)
            raise LLMGenerationError(f"Gemini API provider error: {sanitized_msg}")

        candidates = data.get("candidates")
        if not candidates or not isinstance(candidates, list):
            prompt_feedback = data.get("promptFeedback")
            if prompt_feedback and isinstance(prompt_feedback, dict):
                block_reason = prompt_feedback.get("blockReason", "BLOCKED")
                raise LLMGenerationError(f"Gemini generation blocked by safety filters: {block_reason}")
            raise LLMGenerationError("Gemini API response contained no candidate outputs")

        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):
            raise LLMGenerationError("Malformed candidate in Gemini API response")

        finish_reason = first_candidate.get("finishReason")
        if finish_reason and finish_reason not in ("STOP", "MAX_TOKENS"):
            raise LLMGenerationError(f"Gemini generation halted with finish reason: {finish_reason}")

        content = first_candidate.get("content")
        if not content or not isinstance(content, dict):
            raise LLMGenerationError("Gemini candidate missing content payload")

        parts = content.get("parts")
        if not parts or not isinstance(parts, list):
            raise LLMGenerationError("Gemini candidate content missing parts list")

        text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
        generated_text = "".join(text_parts).strip()

        if not generated_text:
            raise LLMGenerationError("Gemini API returned empty text in candidate content")

        return DraftResult(
            text=generated_text,
            provider="gemini",
            model=self.model,
            raw_prompt=prompt,
        )
