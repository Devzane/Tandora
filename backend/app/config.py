"""Centralized application configuration and on-demand credential validation."""

import re
import secrets
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CHROME_EXTENSION_ID_PATTERN = re.compile(r"^[a-p]{32}$")


class MissingCredentialError(RuntimeError):
    """Raised when an unconfigured external service is invoked."""
    pass


class Settings(BaseSettings):
    # Application & Server Core Settings
    database_path: str = "./data/tandora.db"
    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8000
    extension_api_secret: str = Field(
        default_factory=lambda: secrets.token_hex(32),
        description="Shared secret header for Chrome Extension API requests. Configurable via EXTENSION_API_SECRET.",
    )
    chrome_extension_id: str = "doaipkncpfpmingeoanfpealbjojkmlp"
    daily_sending_limit: int = 20
    dry_run: bool = True

    @field_validator("chrome_extension_id", mode="after")
    @classmethod
    def validate_chrome_extension_id(cls, v: str) -> str:
        cleaned = v.strip().lower() if v else ""
        if not CHROME_EXTENSION_ID_PATTERN.match(cleaned):
            raise ValueError(
                f"Invalid Chrome extension ID: '{v}'. Expected 32 lowercase characters between 'a' and 'p' (matching ^[a-p]{{32}}$)."
            )
        return cleaned

    # AI / LLM Configuration
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"

    # Reoon Email Verification
    reoon_api_key: str | None = None

    # Zoho Mail (SMTP / IMAP)
    zoho_smtp_host: str = "smtp.zoho.com"
    zoho_smtp_port: int = 587
    zoho_smtp_username: str | None = None
    zoho_smtp_password: str | None = None
    zoho_sender_email: str | None = None
    zoho_imap_host: str = "imap.zoho.com"
    zoho_imap_port: int = 993

    # Google Sheets Integration
    google_credentials_path: str | None = None
    google_sheets_id: str | None = None

    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def validate_gemini_credentials(self) -> str:
        """Validate Gemini API key on-demand when drafting is invoked."""
        if not self.gemini_api_key or not self.gemini_api_key.strip():
            raise MissingCredentialError(
                "Gemini API key is unconfigured. Set GEMINI_API_KEY in your .env file."
            )
        return self.gemini_api_key

    def validate_reoon_credentials(self) -> str:
        """Validate Reoon API key on-demand when email verification is invoked."""
        if not self.reoon_api_key or not self.reoon_api_key.strip():
            raise MissingCredentialError(
                "Reoon API key is unconfigured. Set REOON_API_KEY in your .env file."
            )
        return self.reoon_api_key

    def validate_zoho_smtp_credentials(self) -> tuple[str, str, str]:
        """Validate Zoho SMTP credentials on-demand when live sending is initiated."""
        if not self.zoho_smtp_username or not self.zoho_smtp_password or not self.zoho_sender_email:
            raise MissingCredentialError(
                "Zoho SMTP credentials incomplete. Configure ZOHO_SMTP_USERNAME, "
                "ZOHO_SMTP_PASSWORD, and ZOHO_SENDER_EMAIL in .env."
            )
        return self.zoho_smtp_username, self.zoho_smtp_password, self.zoho_sender_email

    def validate_zoho_imap_credentials(self) -> tuple[str, str]:
        """Validate Zoho IMAP credentials on-demand when inbox polling is invoked."""
        if not self.zoho_smtp_username or not self.zoho_smtp_password:
            raise MissingCredentialError(
                "Zoho IMAP credentials incomplete. Configure ZOHO_SMTP_USERNAME and "
                "ZOHO_SMTP_PASSWORD in .env."
            )
        return self.zoho_smtp_username, self.zoho_smtp_password

    def validate_google_sheets_credentials(self) -> tuple[str, str]:
        """Validate Google Sheets credentials on-demand when sync is invoked."""
        if not self.google_credentials_path or not self.google_sheets_id:
            raise MissingCredentialError(
                "Google Sheets credentials incomplete. Configure GOOGLE_CREDENTIALS_PATH "
                "and GOOGLE_SHEETS_ID in .env."
            )
        return self.google_credentials_path, self.google_sheets_id


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
