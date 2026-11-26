"""LLM Provider Interface, result structures, and generation exceptions."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LLMGenerationError(Exception):
    """Raised when an LLM provider generation request fails, times out, or returns invalid data."""
    pass


@dataclass(frozen=True)
class DraftResult:
    """Immutable result from an LLM generation invocation."""

    text: str
    provider: str
    model: str
    raw_prompt: str | None = None

    @property
    def content(self) -> str:
        """Alias for generated text content."""
        return self.text

    @property
    def model_used(self) -> str:
        """Alias for model identifier."""
        return self.model


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol defining the generation contract for all LLM providers."""

    def generate(self, prompt: str) -> DraftResult:
        """Generate draft text from a prompt.

        Args:
            prompt: Formatted prompt instructions and entity context.

        Returns:
            DraftResult containing the generated text, provider, and model.

        Raises:
            LLMGenerationError: On network failures, timeouts, provider errors, or empty responses.
        """
        ...
