---
name: llm-integration
description: Gemini API and Ollama integration for Tandora — provider abstraction, prompt engineering, structured output validation, and hallucination prevention.
risk: low
source: project
date_added: '2026-11-21'
---

# LLM Integration Skill — Tandora

## Purpose

This skill covers AI-powered email draft generation in Tandora: the provider abstraction layer, prompt construction, calling Gemini or Ollama, validating generated output, and storing versioned drafts.

## When to Use

Read this skill before implementing `integrations/gemini.py`, `integrations/ollama.py`, `providers/llm_interface.py`, or `services/draft_service.py`.

## Required Engineering Practices

### Provider Interface

Define a protocol that both Gemini and Ollama clients must implement:

```python
# app/providers/llm_interface.py
from typing import Protocol

class DraftResult:
    def __init__(self, subject: str, body: str, model_used: str):
        self.subject = subject
        self.body = body
        self.model_used = model_used

class LLMProvider(Protocol):
    def generate_draft(self, prompt: str) -> DraftResult:
        """Generate an email draft from a prompt. Raises LLMGenerationError on failure."""
        ...

class LLMGenerationError(Exception):
    pass
```

### Provider Factory

```python
# app/providers/llm_factory.py
from app.config import get_settings
from app.integrations.gemini import GeminiProvider
from app.integrations.ollama import OllamaProvider
from app.providers.llm_interface import LLMProvider

def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "gemini":
        return GeminiProvider(api_key=settings.gemini_api_key)
    elif settings.llm_provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url)
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
```

### Gemini Provider

```python
# app/integrations/gemini.py
import google.generativeai as genai
from app.providers.llm_interface import DraftResult, LLMGenerationError

class GeminiProvider:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def generate_draft(self, prompt: str) -> DraftResult:
        try:
            response = self.model.generate_content(prompt)
            subject, body = parse_draft_output(response.text)
            validate_draft(subject, body)
            return DraftResult(subject=subject, body=body, model_used="gemini-1.5-flash")
        except Exception as e:
            raise LLMGenerationError(f"Gemini generation failed: {e}") from e
```

### Ollama Provider

```python
# app/integrations/ollama.py
import httpx
from app.providers.llm_interface import DraftResult, LLMGenerationError

class OllamaProvider:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def generate_draft(self, prompt: str) -> DraftResult:
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": "llama3.2", "prompt": prompt, "stream": False}
                )
                response.raise_for_status()
                text = response.json().get("response", "")
                subject, body = parse_draft_output(text)
                validate_draft(subject, body)
                return DraftResult(subject=subject, body=body, model_used="llama3.2")
        except httpx.RequestError as e:
            raise LLMGenerationError(f"Ollama unavailable: {e}") from e
```

### Prompt Engineering

The prompt must instruct the LLM to return structured output. Use a fixed format to make parsing reliable:

```python
PROMPT_TEMPLATE = """
You are writing a professional {email_type} email on behalf of {sender_name}.

Context:
- Target company: {company_name}
- Company description: {company_description}
- Opportunity: {opportunity_title}
- Opportunity details: {opportunity_description}
- Contact name: {contact_first_name} {contact_last_name}
- Contact role: {contact_roles}
- Additional notes: {contact_notes}
- Sender background: {sender_background}

Write a concise, professional, personalized email. Do not use generic filler phrases.
Do not make up specific facts about the contact or company not provided above.

Output format (use exactly these labels):
SUBJECT: <subject line here>
BODY:
<email body here>
"""
```

### Output Parsing & Validation

```python
def parse_draft_output(text: str) -> tuple[str, str]:
    lines = text.strip().split("\n")
    subject = None
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("SUBJECT:"):
            subject = line[len("SUBJECT:"):].strip()
        elif line.startswith("BODY:"):
            in_body = True
        elif in_body:
            body_lines.append(line)

    if not subject or not body_lines:
        raise LLMGenerationError("LLM output did not match expected SUBJECT: / BODY: format")

    return subject, "\n".join(body_lines).strip()

def validate_draft(subject: str, body: str) -> None:
    if len(subject) < 5 or len(subject) > 200:
        raise LLMGenerationError(f"Subject length invalid: {len(subject)}")
    if len(body) < 50 or len(body) > 2000:
        raise LLMGenerationError(f"Body length invalid: {len(body)}")
    for placeholder in ["[COMPANY]", "[NAME]", "[INSERT]", "{{", "}}"]:
        if placeholder in body or placeholder in subject:
            raise LLMGenerationError(f"Draft contains unfilled placeholder: {placeholder}")
```

## Common Mistakes

- Calling the LLM without validating the output format. → Always validate.
- Assuming the LLM returns consistent formatting. → Parse defensively with strict boundary checks.
- Including entire database dumps as context in prompts. → Use only relevant entity fields.
- Hardcoding the model name in business logic. → Keep models configurable.
- Silently falling back to Gemini if Ollama fails. → Raise an error; do not silently switch providers.

## Security Considerations

- Do not include credentials, file paths, or internal connection strings in LLM prompts.
- Treat LLM output as untrusted content: validate length, encoding, and absence of placeholders.
- Do not expose raw LLM API errors to client API responses. Log internally and return a sanitized error message.
- The `generation_prompt` stored in the `drafts` table is for audit purposes. Ensure credentials are never injected into prompt strings.

## Testing Requirements

- Mock the LLM provider in all tests using the `LLMProvider` interface.
- Test successful generation with valid output parsing.
- Test malformed output (missing SUBJECT or BODY) raising `LLMGenerationError`.
- Test output that fails validation (too short, too long, contains placeholder).
- Test provider switching: switching config changes the provider instantiated.
- Test that a failed generation does not create a draft record.

## Project-Specific Constraints

- Gemini API is the primary provider; Ollama is optional local inference.
- Provider switching requires only a configuration change.
- Each generation creates a new draft version; previous versions remain immutable for audit.
