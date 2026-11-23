"""Authentication dependencies for Tandora."""

import secrets
from fastapi import Header, HTTPException, Request, status
from app.config import get_settings


def require_extension_secret(
    request: Request,
    x_extension_secret: str | None = Header(None, alias="X-Extension-Secret"),
) -> str:
    """Validate extension identity and shared secret header for local Chrome Extension API calls.
    
    1. If the request carries a chrome-extension:// Origin header, verify that it matches
       the expected Tandora extension ID. Rejects unexpected extension IDs with 403 Forbidden.
    2. Independently validates the X-Extension-Secret header against the server configuration
       using constant-time comparison (secrets.compare_digest).
       Returns 401 Unauthorized if missing or mismatched.
    """
    settings = get_settings()

    # 1. Defense-in-depth: If request originates from an extension, enforce Tandora's extension ID
    origin = request.headers.get("origin")
    if origin and origin.startswith("chrome-extension://"):
        ext_id = origin.replace("chrome-extension://", "").split("/")[0].lower()
        if not ext_id or ext_id != settings.chrome_extension_id.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized extension origin: '{origin}'",
            )

    # 2. Independent secret validation using constant-time comparison
    if not settings.extension_api_secret or not settings.extension_api_secret.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server extension API secret is unconfigured",
        )

    is_valid = False
    if x_extension_secret and isinstance(x_extension_secret, str):
        cleaned_secret = x_extension_secret.strip()
        if cleaned_secret:
            try:
                # Python's secrets.compare_digest raises TypeError on non-ASCII strings.
                # If both are ASCII, compare directly; otherwise compare as UTF-8 bytes to
                # safely preserve constant-time comparison without unhandled exceptions.
                if cleaned_secret.isascii() and settings.extension_api_secret.isascii():
                    is_valid = secrets.compare_digest(cleaned_secret, settings.extension_api_secret)
                else:
                    is_valid = secrets.compare_digest(
                        cleaned_secret.encode("utf-8"),
                        settings.extension_api_secret.encode("utf-8"),
                    )
            except Exception:
                is_valid = False

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing extension secret",
        )

    return x_extension_secret
