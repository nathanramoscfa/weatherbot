# src/weatherbot/web/guards.py
"""Loopback host, fetch-metadata, same-origin write, and security-header ASGI guards.

Every custom guard is a pure ASGI middleware over ``(scope, receive, send)``. Outermost is
``SecurityHeadersMiddleware``, so even a ``400`` response from ``TrustedHostMiddleware``
carries the full security header set and ``Cache-Control: no-store`` on ``/api/`` paths.
"""

from typing import Final

from fastapi import FastAPI
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ALLOWED_HOSTS: Final[tuple[str, ...]] = ("127.0.0.1", "localhost", "[::1]")
WRITE_METHODS: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SAFE_API_FETCH_SITES: Final[frozenset[str]] = frozenset({"same-origin", "none"})

CSP_DEFAULT_STYLE: Final = "style-src 'self'"
CSP_SUFFIX: Final = (
    "img-src 'self' data: https://tile.openstreetmap.org; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
DEFAULT_CSP: Final = f"default-src 'self'; script-src 'self'; {CSP_DEFAULT_STYLE}; {CSP_SUFFIX}"

FIXED_SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Permissions-Policy", "geolocation=(), camera=(), microphone=()"),
)
NO_STORE: Final = "no-store"


def csp_header(nonce: str | None = None) -> str:
    """Build the Content-Security-Policy header value, optionally with a style nonce."""
    if nonce is None:
        return DEFAULT_CSP
    style = f"style-src 'self' 'nonce-{nonce}'"
    return f"default-src 'self'; script-src 'self'; {style}; {CSP_SUFFIX}"


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class SecurityHeadersMiddleware:
    """Outermost pure ASGI middleware applying security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach security headers and ``Cache-Control: no-store`` on ``/api/`` responses."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        is_api = _is_api_path(path)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "content-security-policy" not in headers:
                    headers["Content-Security-Policy"] = DEFAULT_CSP
                for name, value in FIXED_SECURITY_HEADERS:
                    headers[name] = value
                if is_api:
                    headers["Cache-Control"] = NO_STORE
                for existing in list(headers.keys()):
                    if existing.lower().startswith("access-control-allow-"):
                        del headers[existing]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class FetchMetadataAndWriteGuard:
    """Pure ASGI guard for ``OPTIONS``, ``Sec-Fetch-Site``, ``Origin``, and JSON writes."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce same-origin fetch metadata and ``application/json`` on writes."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        if method == "OPTIONS":
            response = JSONResponse({"detail": "Method Not Allowed"}, status_code=405)
            await response(scope, receive, send)
            return

        headers = Headers(scope=scope)
        path = str(scope.get("path", ""))
        fetch_site_raw = headers.get("sec-fetch-site")
        fetch_site = fetch_site_raw.strip().lower() if fetch_site_raw is not None else None

        if _is_api_path(path) and fetch_site is not None and fetch_site not in SAFE_API_FETCH_SITES:
            response = JSONResponse(
                {"detail": "Cross-site API request refused"},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        if method in WRITE_METHODS:
            if fetch_site is not None and fetch_site != "same-origin":
                response = JSONResponse(
                    {"detail": "Cross-site write request refused"},
                    status_code=403,
                )
                await response(scope, receive, send)
                return

            origin = headers.get("origin")
            if origin is not None:
                host = headers.get("host", "").strip().lower()
                expected_origin = f"http://{host}"
                if origin.strip().lower() != expected_origin:
                    response = JSONResponse(
                        {"detail": "Cross-origin write request refused"},
                        status_code=403,
                    )
                    await response(scope, receive, send)
                    return

            content_type = headers.get("content-type", "")
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                response = JSONResponse(
                    {"detail": "Content-Type must be application/json"},
                    status_code=415,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def install_guards(app: FastAPI) -> None:
    """Mount the write/fetch-metadata guard, ``TrustedHostMiddleware``, and security headers.

    Starlette's ``add_middleware`` wraps in reverse order of registration, so registering
    ``SecurityHeadersMiddleware`` last makes it the outermost wrapper around
    ``TrustedHostMiddleware``.
    """
    app.add_middleware(FetchMetadataAndWriteGuard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ALLOWED_HOSTS))
    app.add_middleware(SecurityHeadersMiddleware)
