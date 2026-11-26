"""Automated tests for LLM provider abstraction, Gemini and Ollama clients, and factory resolution."""

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import MissingCredentialError, Settings
from app.integrations.gemini import GeminiProvider, _sanitize_provider_message
from app.integrations.ollama import OllamaProvider, _sanitize_error_message
from app.providers.llm_factory import get_llm_provider
from app.providers.llm_interface import DraftResult, LLMGenerationError, LLMProvider


# ==============================================================================
# 1. Interface and Protocol Conformance Tests
# ==============================================================================


def test_draft_result_immutability_and_aliases():
    """Verify DraftResult is frozen and provides .content and .model_used property aliases."""
    result = DraftResult(
        text="Dear Alex, loved your work on robotics.",
        provider="gemini",
        model="gemini-1.5-flash",
        raw_prompt="Write an email to Alex",
    )

    assert result.text == "Dear Alex, loved your work on robotics."
    assert result.content == "Dear Alex, loved your work on robotics."
    assert result.provider == "gemini"
    assert result.model == "gemini-1.5-flash"
    assert result.model_used == "gemini-1.5-flash"
    assert result.raw_prompt == "Write an email to Alex"

    with pytest.raises(FrozenInstanceError):
        result.text = "Modified text"


def test_provider_protocol_runtime_checkable():
    """Verify GeminiProvider and OllamaProvider satisfy the LLMProvider runtime protocol."""
    gemini = GeminiProvider(api_key="dummy_key", model="gemini-3.5-flash-lite")
    ollama = OllamaProvider(base_url="http://127.0.0.1:11434", model="llama3.2")

    assert isinstance(gemini, LLMProvider)
    assert isinstance(ollama, LLMProvider)


def test_gemini_default_model_is_gemini_3_5_flash_lite():
    """Verify that the default Gemini model is gemini-3.5-flash-lite when unconfigured."""
    # Field default in Pydantic Settings schema
    assert Settings.model_fields["gemini_model"].default == "gemini-3.5-flash-lite"

    # Provider instantiation without explicit model inherits default from Settings
    with patch("app.integrations.gemini.get_settings") as mock_settings_fn:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.gemini_model = "gemini-3.5-flash-lite"
        mock_settings.validate_gemini_credentials.return_value = "dummy_key"
        mock_settings.llm_timeout_seconds = 60.0
        mock_settings_fn.return_value = mock_settings

        provider = GeminiProvider(api_key="dummy_key")
        assert provider.model == "gemini-3.5-flash-lite"
        assert provider.endpoint_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"


def test_gemini_explicit_model_configuration():
    """Verify that explicitly configured model names (e.g., gemini-3.8-flash) still work."""
    # Direct provider instantiation with explicit model override
    provider = GeminiProvider(api_key="dummy_key", model="gemini-3.8-flash")
    assert provider.model == "gemini-3.8-flash"
    assert provider.endpoint_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"

    # Factory instantiation with explicit model override
    factory_provider = get_llm_provider("gemini", api_key="dummy_key", model="gemini-3.8-flash")
    assert isinstance(factory_provider, GeminiProvider)
    assert factory_provider.model == "gemini-3.8-flash"


# ==============================================================================
# 2. Google Gemini REST Client Tests
# ==============================================================================


def test_gemini_provider_successful_generation():
    """Verify GeminiProvider formats request correctly and parses candidate content."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Subject: Opportunity\n\nHi Sarah, great to connect."}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20},
    }

    with patch("app.integrations.gemini.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_response

        provider = GeminiProvider(
            api_key="AIzaSy_SECRET_KEY_123",
            model="gemini-3.5-flash-lite",
            timeout=45.0,
        )
        res = provider.generate("Generate an outreach message for Sarah.")

        assert res.provider == "gemini"
        assert res.model == "gemini-3.5-flash-lite"
        assert "Hi Sarah, great to connect." in res.text
        assert res.raw_prompt == "Generate an outreach message for Sarah."

        # Verify endpoint and header authentication
        mock_client.post.assert_called_once()
        call_args, call_kwargs = mock_client.post.call_args
        target_url = call_args[0]

        # Key MUST be in headers, NEVER in URL
        assert "AIzaSy_SECRET_KEY_123" not in target_url
        assert call_kwargs["headers"]["x-goog-api-key"] == "AIzaSy_SECRET_KEY_123"
        assert call_kwargs["json"]["contents"][0]["parts"][0]["text"] == "Generate an outreach message for Sarah."


def test_gemini_provider_rejects_empty_prompt():
    """Verify GeminiProvider rejects empty or whitespace-only prompts."""
    provider = GeminiProvider(api_key="dummy_key")
    with pytest.raises(LLMGenerationError, match="Prompt must not be empty"):
        provider.generate("   ")


def test_gemini_provider_timeout_handling():
    """Verify timeout produces sanitized LLMGenerationError with decoupled context."""
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent")
    timeout_exc = httpx.ReadTimeout("Read timed out after 60s", request=req)

    with patch("app.integrations.gemini.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = timeout_exc

        provider = GeminiProvider(api_key="test_key", timeout=60.0)
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate("Test prompt")

        assert "timed out after 60.0s" in str(exc_info.value)
        assert exc_info.value.__context__ is None


def test_gemini_provider_connection_error_handling():
    """Verify connection failure produces sanitized LLMGenerationError with decoupled context."""
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent")
    conn_exc = httpx.ConnectError("Failed to establish a new connection", request=req)

    with patch("app.integrations.gemini.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = conn_exc

        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate("Test prompt")

        assert "Could not connect to Gemini API" in str(exc_info.value)
        assert exc_info.value.__context__ is None


def test_gemini_provider_http_error_sanitization():
    """Verify HTTP non-200 responses are sanitized and do not leak credentials."""
    secret_key = "AIzaSy_HIGHLY_CONFIDENTIAL_KEY"
    fake_response = MagicMock()
    fake_response.status_code = 400
    fake_response.text = f"API error with key={secret_key} and url=https://generativelanguage.googleapis.com?key={secret_key}"
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=fake_response
    )

    with patch("app.integrations.gemini.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_response

        provider = GeminiProvider(api_key=secret_key)
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate("Test prompt")

        err_msg = str(exc_info.value)
        assert "Gemini API returned HTTP 400" in err_msg
        assert secret_key not in err_msg
        assert "[REDACTED]" in err_msg
        assert exc_info.value.__context__ is None


def test_gemini_provider_defensive_parsing_empty_candidates():
    """Verify provider raises LLMGenerationError when candidates list is empty."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"candidates": []}

    with patch("app.integrations.gemini.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_response

        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(LLMGenerationError, match="contained no candidate outputs"):
            provider.generate("Test prompt")


def test_gemini_provider_defensive_parsing_safety_blocked():
    """Verify provider raises LLMGenerationError when generation is blocked by safety filters."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [
            {
                "finishReason": "SAFETY",
                "content": {"parts": []},
            }
        ]
    }

    with patch("app.integrations.gemini.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_response

        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(LLMGenerationError, match="finish reason: SAFETY"):
            provider.generate("Test prompt")


# ==============================================================================
# 3. Local Ollama REST Client Tests
# ==============================================================================


def test_ollama_provider_successful_generation():
    """Verify OllamaProvider calls /api/generate with stream=False and returns DraftResult."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "model": "llama3.2",
        "created_at": "2026-11-26T12:00:00Z",
        "response": "Subject: Partnership Inquiry\n\nHi Jordan, let's connect.",
        "done": True,
    }

    with patch("app.integrations.ollama.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_response

        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434",
            model="llama3.2",
            timeout=30.0,
        )
        res = provider.generate("Generate an email for Jordan.")

        assert res.provider == "ollama"
        assert res.model == "llama3.2"
        assert "Hi Jordan, let's connect." in res.text
        assert res.raw_prompt == "Generate an email for Jordan."

        mock_client.post.assert_called_once_with(
            "http://127.0.0.1:11434/api/generate",
            json={"model": "llama3.2", "prompt": "Generate an email for Jordan.", "stream": False},
            headers={"Content-Type": "application/json"},
        )


def test_ollama_provider_rejects_empty_prompt():
    """Verify OllamaProvider rejects empty or whitespace-only prompts."""
    provider = OllamaProvider()
    with pytest.raises(LLMGenerationError, match="Prompt must not be empty"):
        provider.generate("   ")


def test_ollama_provider_unavailability_handling():
    """Verify OllamaProvider returns clear error message when Ollama daemon is offline."""
    req = httpx.Request("POST", "http://127.0.0.1:11434/api/generate")
    conn_exc = httpx.ConnectError("Connection refused", request=req)

    with patch("app.integrations.ollama.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = conn_exc

        provider = OllamaProvider(base_url="http://127.0.0.1:11434")
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate("Test prompt")

        err_msg = str(exc_info.value)
        assert "Ollama service unavailable at http://127.0.0.1:11434" in err_msg
        assert "Ensure Ollama is running locally" in err_msg
        assert exc_info.value.__context__ is None


def test_ollama_provider_timeout_handling():
    """Verify OllamaProvider handles generation timeouts gracefully."""
    req = httpx.Request("POST", "http://127.0.0.1:11434/api/generate")
    timeout_exc = httpx.ReadTimeout("Timeout", request=req)

    with patch("app.integrations.ollama.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = timeout_exc

        provider = OllamaProvider(timeout=15.0)
        with pytest.raises(LLMGenerationError) as exc_info:
            provider.generate("Test prompt")

        assert "timed out after 15.0s" in str(exc_info.value)
        assert exc_info.value.__context__ is None


def test_ollama_provider_defensive_parsing_empty_response():
    """Verify OllamaProvider raises LLMGenerationError when 'response' is empty or missing."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"model": "llama3.2", "response": "", "done": True}

    with patch("app.integrations.ollama.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_response

        provider = OllamaProvider()
        with pytest.raises(LLMGenerationError, match="returned an empty response"):
            provider.generate("Test prompt")


# ==============================================================================
# 4. LLM Factory and Dynamic Resolution Tests
# ==============================================================================


def test_factory_resolves_default_gemini_from_settings():
    """Verify get_llm_provider defaults to Gemini when configured in Settings."""
    with patch("app.providers.llm_factory.get_settings") as mock_settings_fn:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.llm_provider = "gemini"
        mock_settings.gemini_model = "gemini-3.5-flash-lite"
        mock_settings.llm_timeout_seconds = 60.0
        mock_settings.validate_gemini_credentials.return_value = "key_from_settings"
        mock_settings_fn.return_value = mock_settings

        with patch("app.integrations.gemini.get_settings", return_value=mock_settings):
            provider = get_llm_provider()
            assert isinstance(provider, GeminiProvider)
            assert provider.model == "gemini-3.5-flash-lite"
            assert provider.api_key == "key_from_settings"


def test_factory_resolves_ollama_when_explicitly_requested():
    """Verify get_llm_provider returns OllamaProvider without mutating global settings."""
    with patch("app.providers.llm_factory.get_settings") as mock_settings_fn:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.llm_provider = "gemini"  # Global setting is Gemini
        mock_settings.ollama_base_url = "http://127.0.0.1:11434"
        mock_settings.ollama_model = "llama3.2"
        mock_settings.llm_timeout_seconds = 60.0
        mock_settings_fn.return_value = mock_settings

        with patch("app.integrations.ollama.get_settings", return_value=mock_settings):
            provider = get_llm_provider(
                provider_name="ollama",
                model="mistral",
                timeout=30.0,
            )
            assert isinstance(provider, OllamaProvider)
            assert provider.model == "mistral"
            assert provider.timeout == 30.0
            # Global settings was NOT mutated
            assert mock_settings.llm_provider == "gemini"


def test_factory_raises_value_error_for_unsupported_provider():
    """Verify get_llm_provider rejects unsupported providers with helpful message."""
    with pytest.raises(ValueError, match="Unsupported LLM provider: 'anthropic'"):
        get_llm_provider(provider_name="anthropic")


def test_factory_lazy_validation_missing_gemini_credentials():
    """Verify missing Gemini credentials raise MissingCredentialError at resolution time."""
    with patch("app.providers.llm_factory.get_settings") as mock_settings_fn:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.llm_provider = "gemini"
        mock_settings.validate_gemini_credentials.side_effect = MissingCredentialError(
            "Gemini API key is unconfigured. Set GEMINI_API_KEY in your .env file."
        )
        mock_settings_fn.return_value = mock_settings

        with patch("app.integrations.gemini.get_settings", return_value=mock_settings):
            with pytest.raises(MissingCredentialError, match="Gemini API key is unconfigured"):
                get_llm_provider()


def test_factory_case_insensitive_provider_names():
    """Verify provider names are resolved case-insensitively."""
    with patch("app.providers.llm_factory.get_settings") as mock_settings_fn:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ollama_base_url = "http://127.0.0.1:11434"
        mock_settings.ollama_model = "llama3.2"
        mock_settings.llm_timeout_seconds = 60.0
        mock_settings_fn.return_value = mock_settings

        with patch("app.integrations.ollama.get_settings", return_value=mock_settings):
            provider = get_llm_provider(provider_name="OLLAMA")
            assert isinstance(provider, OllamaProvider)
