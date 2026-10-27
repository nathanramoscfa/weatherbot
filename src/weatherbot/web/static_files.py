# src/weatherbot/web/static_files.py
"""In-memory serving of the built web interface and the unbuilt fallback page.

When ``static_dir`` holds ``index.html``, ``load_static_bundle`` walks ``static_dir`` once at
app creation and caches every asset in memory with its content-type and ``Cache-Control``
policy. No request touches the filesystem after startup.
"""

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from starlette.responses import HTMLResponse, JSONResponse, Response

from weatherbot.services.disclaimer import NOTICE
from weatherbot.web.guards import NO_STORE, csp_header

DEFAULT_STATIC_DIR: Final = Path(__file__).resolve().parent / "static"
IMMUTABLE_CACHE: Final = "public, max-age=31536000, immutable"
NO_CACHE: Final = "no-cache"
CSP_NONCE_PLACEHOLDER: Final = "__CSP_NONCE__"
INDEX_SHA256_PREFIX_LEN: Final = 12

MEDIA_TYPES: Final[dict[str, str]] = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".mjs": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
}

UNBUILT_HTML: Final = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Weatherbot — Web interface not built</title>
  </head>
  <body>
    <main>
      <h1>Weatherbot web interface is not built</h1>
      <p>
        This checkout does not yet have a built frontend bundle in
        <code>src/weatherbot/web/static/index.html</code>.
      </p>
      <p>
        See <code>CONTRIBUTING.md</code> for the frontend build instructions
        (<code>npm --prefix web ci &amp;&amp; npm --prefix web run build</code>).
        The local JSON API is active at <a href="/api/health"><code>/api/health</code></a>.
      </p>
      <footer><small>{NOTICE}</small></footer>
    </main>
  </body>
</html>
"""


@dataclass(frozen=True)
class StaticAsset:
    """One static file cached in memory at application startup."""

    content: bytes
    media_type: str
    cache_control: str


@dataclass(frozen=True)
class StaticBundle:
    """The in-memory built interface bundle loaded once at startup."""

    present: bool
    index_sha256: str | None
    index_template: str | None
    files: dict[str, StaticAsset]


def _media_type(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def load_static_bundle(static_dir: Path | None = None) -> StaticBundle:
    """Walk ``static_dir`` once and load ``index.html`` and all static assets into memory."""
    directory = DEFAULT_STATIC_DIR if static_dir is None else static_dir
    index_path = directory / "index.html"
    if not directory.is_dir() or not index_path.is_file():
        return StaticBundle(
            present=False,
            index_sha256=None,
            index_template=None,
            files={},
        )

    index_bytes = index_path.read_bytes()
    index_sha256 = hashlib.sha256(index_bytes).hexdigest()[:INDEX_SHA256_PREFIX_LEN]
    index_template = index_bytes.decode("utf-8")

    files: dict[str, StaticAsset] = {}
    for file_path in sorted(directory.rglob("*")):
        if not file_path.is_file() or file_path == index_path:
            continue
        rel_posix = "/" + file_path.relative_to(directory).as_posix()
        cache_control = (
            IMMUTABLE_CACHE
            if rel_posix == "/assets" or rel_posix.startswith("/assets/")
            else NO_CACHE
        )
        files[rel_posix] = StaticAsset(
            content=file_path.read_bytes(),
            media_type=_media_type(file_path),
            cache_control=cache_control,
        )

    return StaticBundle(
        present=True,
        index_sha256=index_sha256,
        index_template=index_template,
        files=files,
    )


def _serve_index_or_fallback(bundle: StaticBundle) -> HTMLResponse:
    if not bundle.present or bundle.index_template is None:
        return HTMLResponse(
            content=UNBUILT_HTML,
            status_code=200,
            headers={"Cache-Control": NO_STORE},
        )
    nonce = secrets.token_urlsafe(16)
    rendered = bundle.index_template.replace(CSP_NONCE_PLACEHOLDER, nonce)
    return HTMLResponse(
        content=rendered,
        status_code=200,
        headers={
            "Cache-Control": NO_STORE,
            "Content-Security-Policy": csp_header(nonce),
        },
    )


def install_static_routes(app: FastAPI, bundle: StaticBundle) -> None:
    """Register the ``/api/*`` JSON 404 fallback and the in-memory UI routes."""

    @app.api_route(
        "/api",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
        include_in_schema=False,
    )
    @app.api_route(
        "/api/{rest:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
        include_in_schema=False,
    )
    def api_not_found(rest: str = "") -> JSONResponse:
        del rest
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    @app.get("/", include_in_schema=False)
    def root_page() -> Response:
        return _serve_index_or_fallback(bundle)

    @app.get("/{full_path:path}", include_in_schema=False)
    def ui_or_asset(full_path: str) -> Response:
        url_path = "/" + full_path.lstrip("/")
        if url_path == "/api" or url_path.startswith("/api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if not bundle.present:
            return _serve_index_or_fallback(bundle)
        asset = bundle.files.get(url_path)
        if asset is not None:
            return Response(
                content=asset.content,
                media_type=asset.media_type,
                headers={"Cache-Control": asset.cache_control},
            )
        if url_path == "/assets" or url_path.startswith("/assets/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return _serve_index_or_fallback(bundle)
