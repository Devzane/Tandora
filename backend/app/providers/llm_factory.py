"""LLM Provider Factory.

Dynamically instantiates and returns configured LLM provider implementations
without mutating global application settings or performing premature network calls.
"""

from typing import Any
from app.config import get_settings
from app.providers.llm_interface import LLMProvider

SUPPORTED_PROVIDERS = ("gemini", "ollama")


def get_llm_provider(
    provider_name: str | None = None,
    **kwargs: Any,
) -> LLMProvider:
    """Resolve and return an initialized LLMProvider instance.

    Args:
        provider_name: Name of the provider ('gemini' or 'ollama').
                       If None, defaults to `settings.llm_provider`.
        **kwargs: Optional provider-specific overrides:
                  For Gemini: api_key, model, timeout
                  For Ollama: base_url, model, timeout

    Returns:
        An instance conforming to the LLMProvider protocol.

    Raises:
        ValueError: If provider_name is not supported.
        MissingCredentialError: If the requested provider requires credentials
                                that are missing from settings and kwargs.
    """
    settings = get_settings()
    target_provider = (provider_name or settings.llm_provider).strip().lower()

    if target_provider == "gemini":
        from app.integrations.gemini import GeminiProvider

        return GeminiProvider(
            api_key=kwargs.get("api_key"),
            model=kwargs.get("model"),
            timeout=kwargs.get("timeout"),
        )
    elif target_provider == "ollama":
        from app.integrations.ollama import OllamaProvider

        return OllamaProvider(
            base_url=kwargs.get("base_url"),
            model=kwargs.get("model"),
            timeout=kwargs.get("timeout"),
        )
    else:
        supported_str = ", ".join(f"'{p}'" for p in SUPPORTED_PROVIDERS)
        raise ValueError(
            f"Unsupported LLM provider: '{target_provider}'. Supported providers: {supported_str}."
        )
