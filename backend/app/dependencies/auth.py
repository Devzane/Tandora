"""Authentication dependencies for Tandora."""

from fastapi import Header, HTTPException, status
from app.config import get_settings


def require_extension_secret(
    x_extension_secret: str | None = Header(None, alias="X-Extension-Secret")
) -> str:
    """Validate shared extension secret header for local Chrome Extension API calls.
    
    Returns 401 Unauthorized if missing or mismatched.
    """
    settings = get_settings()
    if not x_extension_secret or x_extension_secret.strip() != settings.extension_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing extension secret",
        )
    return x_extension_secret
