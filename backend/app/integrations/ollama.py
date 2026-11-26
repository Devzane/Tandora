"""Local Ollama REST API Integration."""

import logging
import re
from typing import Any
import httpx

from app.config import get_settings
from app.providers.llm_interface import DraftResult, LLMGenerationError

logger = logging.getLogger(__name__)


def _sanitize_error_message(msg: Any) -> str:
    """Sanitize error messages to prevent leaking URLs with credentials or control characters."""
    if not msg:
        return "Unknown error"
    text = str(msg).strip()
    text = re.sub(r"(?i)(key|token|secret|password|api[_-]?key)=[^\s&'\"]+", r"\1=[REDACTED]", text)
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    text = " ".join(text.split())
    return text[:200]


class OllamaProvider:
    """Client for generating draft text using local Ollama REST API.

    Calls the local /api/generate endpoint with stream=False for self-hosted,
    offline, and cost-free draft generation.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout if timeout is not None else settings.llm_timeout_seconds

    @property
    def endpoint_url(self) -> str:
        """Return the target REST generate URL."""
        return f"{self.base_url}/api/generate"

    def generate(self, prompt: str) -> DraftResult:
        """Generate text using local Ollama instance.

        Args:
            prompt: Text prompt / instruction.

        Returns:
            DraftResult containing generated text, provider 'ollama', and model.

        Raises:
            LLMGenerationError: If Ollama is unreachable, times out, returns HTTP error,
                                or provides empty/malformed text.
        """
        if not prompt or not prompt.strip():
            raise LLMGenerationError("Prompt must not be empty.")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        target_url = self.endpoint_url
        error_to_raise: LLMGenerationError | None = None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    target_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code != 200:
                    status_code = response.status_code
                    clean_detail = _sanitize_error_message(response.text[:200])
                    error_to_raise = LLMGenerationError(
                        f"Ollama generation failed with status {status_code}: {clean_detail}"
                    )

                if error_to_raise is None:
                    try:
                        data = response.json()
                    except Exception:
                        error_to_raise = LLMGenerationError("Ollama response was not valid JSON.")

                if error_to_raise is None:
                    if not isinstance(data, dict):
                        error_to_raise = LLMGenerationError("Ollama response was not a JSON object.")
                    else:
                        generated_text = data.get("response")
                        if not generated_text or not str(generated_text).strip():
                            error_to_raise = LLMGenerationError("Ollama returned an empty response.")
                        else:
                            return DraftResult(
                                text=str(generated_text).strip(),
                                provider="ollama",
                                model=self.model,
                                raw_prompt=prompt,
                            )

        except httpx.ConnectError:
            clean_url = _sanitize_error_message(self.base_url)
            error_to_raise = LLMGenerationError(
                f"Ollama service unavailable at {clean_url}. Ensure Ollama is running locally."
            )
        except httpx.TimeoutException:
            error_to_raise = LLMGenerationError(
                f"Ollama generation request timed out after {self.timeout}s."
            )
        except httpx.RequestError as exc:
            clean_msg = _sanitize_error_message(str(exc))
            error_to_raise = LLMGenerationError(
                f"Ollama network/request error: {clean_msg}"
            )
        except LLMGenerationError:
            raise
        except Exception as exc:
            clean_msg = _sanitize_error_message(str(exc))
            error_to_raise = LLMGenerationError(
                f"Unexpected error during Ollama generation: {clean_msg}"
            )

        if error_to_raise is not None:
            raise error_to_raise from None

        raise LLMGenerationError("Unexpected termination of Ollama generation request.")
