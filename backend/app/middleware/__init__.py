"""Middleware Package."""

from app.middleware.security import LocalSecurityMiddleware

__all__ = ["LocalSecurityMiddleware"]
