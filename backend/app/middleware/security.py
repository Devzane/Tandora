"""Local security middleware: Origin/Host verification, CSRF defense, and secure headers."""

from urllib.parse import urlparse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from app.config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    """Protects local-first endpoints against browser cross-site request forgery and DNS rebinding."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        allowed_ports = {str(settings.fastapi_port), "8000"}

        # 1. Host Header Validation (DNS Rebinding Defense)
        host_header = request.headers.get("host", "")
        host_name = host_header.split(":")[0].lower() if host_header else ""
        if host_name and host_name not in ALLOWED_HOSTS and host_name != settings.fastapi_host:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Host '{host_name}' is not permitted on local hub."},
            )

        # 2. State-Changing Request Origin / CSRF Defense
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            is_chrome_extension = bool(origin and origin.startswith("chrome-extension://"))

            if not is_chrome_extension:
                sec_fetch_site = request.headers.get("sec-fetch-site")
                if sec_fetch_site == "cross-site":
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Cross-site state-changing requests are prohibited."},
                    )

                if origin:
                    parsed_origin = urlparse(origin)
                    origin_host = (parsed_origin.hostname or "").lower()
                    if origin_host not in ALLOWED_HOSTS and origin_host != settings.fastapi_host:
                        return JSONResponse(
                            status_code=403,
                            content={"detail": f"Cross-origin request from '{origin}' is prohibited."},
                        )

                referer = request.headers.get("referer")
                if not origin and referer:
                    parsed_referer = urlparse(referer)
                    referer_host = (parsed_referer.hostname or "").lower()
                    if referer_host not in ALLOWED_HOSTS and referer_host != settings.fastapi_host:
                        return JSONResponse(
                            status_code=403,
                            content={"detail": f"Cross-origin referer '{referer}' is prohibited."},
                        )

        # Process the request
        response = await call_next(request)

        # 3. Security Hardening Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
