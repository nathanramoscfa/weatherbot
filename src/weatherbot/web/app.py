# src/weatherbot/web/app.py
"""Application factory and shared state for the local FastAPI web application."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from starlette.responses import JSONResponse

from weatherbot import __version__
from weatherbot.services.config import AppPaths, SettingOrigin, Settings
from weatherbot.services.persistence.database import Database
from weatherbot.web.guards import install_guards
from weatherbot.web.routes.health import router as health_router
from weatherbot.web.static_files import install_static_routes, load_static_bundle


@dataclass(frozen=True)
class WebState:
    """Shared dependencies for the local FastAPI application."""

    database: Database
    paths: AppPaths
    settings: Settings
    setting_origins: tuple[SettingOrigin, ...] = ()
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    static_dir: Path | None = None
    corpus: Path | bool | None = None


def _sanitize_validation_errors(errors: Sequence[object]) -> list[dict[str, object]]:
    """Keep only ``loc``, ``msg``, and ``type`` for each error; never echo ``input``."""
    cleaned: list[dict[str, object]] = []
    for item in errors:
        if isinstance(item, dict):
            entry = cast("dict[str, object]", item)
            loc_raw = entry.get("loc", ())
            if isinstance(loc_raw, (list, tuple)):
                loc_items = cast("Sequence[object]", loc_raw)
                loc: list[int | str] = [
                    part if isinstance(part, int) else str(part) for part in loc_items
                ]
            else:
                loc = []
            cleaned.append(
                {
                    "loc": loc,
                    "msg": str(entry.get("msg", "")),
                    "type": str(entry.get("type", "value_error")),
                }
            )
    return cleaned


def create_app(state: WebState) -> FastAPI:
    """Create the local-only FastAPI application with its guards, routes, and static bundle."""
    app = FastAPI(
        title="Weatherbot",
        version=__version__,
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    bundle = load_static_bundle(state.static_dir)
    app.state.web = state
    app.state.static_bundle = bundle

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": _sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(ResponseValidationError)
    async def handle_response_validation_error(
        _request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": _sanitize_validation_errors(exc.errors())},
        )

    install_guards(app)
    app.include_router(health_router)
    install_static_routes(app, bundle)
    return app
